import asyncio
import json
import sys
import time
import traceback
import urllib
from datetime import UTC, datetime, timedelta
from threading import Thread

import conesearch_alchemy as ca
import requests
import sqlalchemy as sa
import tornado.escape
import tornado.ioloop
import tornado.web
from sqlalchemy.orm import scoped_session, sessionmaker

from baselayer.app.env import load_env
from baselayer.app.flow import Flow
from baselayer.app.models import init_db
from baselayer.log import make_log
from skyportal.models import DBSession, Obj
from skyportal.utils.calculations import great_circle_distance
from skyportal.utils.parse import is_null
from skyportal.utils.services import check_loaded
from skyportal.utils.tns import (
    TNS_URL,
    get_IAUname,
    get_recent_TNS,
    get_tns_headers,
    get_tns_url,
)

env, cfg = load_env()
log = make_log("tns_queue")

init_db(**cfg["database"])

Session = scoped_session(sessionmaker())

DEFAULT_RADIUS = 2.0 / 3600  # 2 arcsec in degrees

bot_id = cfg.get("app.tns.bot_id", None)
bot_name = cfg.get("app.tns.bot_name", None)
api_key = cfg.get("app.tns.api_key", None)
look_back_days = cfg.get("app.tns.look_back_days", 1)


def refresh_obj_on_frontend(obj, user_id="*"):
    """Refresh an object's source page on the frontend for all users or a specific user.

    Parameters
    ----------
    obj : `skyportal.models.Obj`
        The object to refresh, with an id and internal_key
    user_id : str, optional
        The user ID to refresh the object for. If '*', refresh for all users.
    """
    try:
        flow = Flow()
        flow.push(
            user_id,
            "skyportal/REFRESH_SOURCE",
            payload={"obj_key": obj.internal_key},
        )
    except Exception:  # noqa: BLE001
        log(f"Error refreshing object {obj.id} on frontend")


def add_tns_name_to_existing_objs(tns_name, tns_source_data, tns_ra, tns_dec, session):
    """Add TNS name to existing objects within 2 arcseconds of the TNS position.

    Parameters
    ----------
    tns_name : str
        TNS name (with prefix) to be added to the object
    tns_source_data : dict
        TNS source data to be added to the object as tns_info
    tns_ra : float
        Right ascension of the TNS source
    tns_dec : float
        Declination of the TNS source
    session : `sqlalchemy.orm.session.Session`
        Database session object
    """
    tns_name = str(tns_name).strip()
    other = ca.Point(ra=tns_ra, dec=tns_dec)
    existing_objs = session.scalars(
        sa.select(Obj).where(Obj.within(other, DEFAULT_RADIUS))  # 2 arcseconds
    ).all()
    if len(existing_objs) > 0:
        for obj in existing_objs:
            try:
                if obj.tns_name == tns_name:
                    continue
                elif obj.tns_name is None or obj.tns_name == "":
                    obj.tns_name = tns_name
                    obj.tns_info = tns_source_data
                # if the obj has tns_info that contains radeg and decdeg,
                # check if the new TNS source is closer to the obj than the existing TNS source
                elif (
                    isinstance(obj.tns_info, dict)
                    and "radeg" in obj.tns_info
                    and "decdeg" in obj.tns_info
                ):
                    existing_tns_dist = great_circle_distance(
                        obj.ra,
                        obj.dec,
                        float(obj.tns_info["radeg"]),
                        float(obj.tns_info["decdeg"]),
                    )
                    new_tns_dist = great_circle_distance(
                        obj.ra, obj.dec, float(tns_ra), float(tns_dec)
                    )
                    if new_tns_dist < existing_tns_dist:
                        obj.tns_name = tns_name
                        obj.tns_info = tns_source_data
                # if the current name doesn't have the SN designation but the new name has it, update
                elif not str(obj.tns_name).lower().strip().startswith(
                    "sn"
                ) and "AT" not in str(tns_name):
                    obj.tns_name = str(tns_name).strip()
                    obj.tns_info = tns_source_data
                else:
                    continue

                session.commit()
                log(f"Updated object {obj.id} with TNS name {tns_name}")
                refresh_obj_on_frontend(obj)
            except Exception as e:  # noqa: BLE001
                log(f"Error updating object: {e!s}")
                session.rollback()


def process_queue(queue):
    """Process the TNS retrieval queue

    Parameters
    ----------
    queue : list
        Tasks to be processed
    """
    if TNS_URL is None or bot_id is None or bot_name is None or api_key is None:
        log("TNS watcher not configured, skipping")
        return
    tns_headers = get_tns_headers(bot_id, bot_name)

    while True:
        if not queue:
            time.sleep(1)
            continue
        task = queue.pop(0)
        if not task:
            continue

        tns_name = None
        existing_obj = None
        try:
            with DBSession() as session:
                if task.get("obj_id") is not None:
                    # here we are looking for the TNS name of an existing object
                    existing_obj = session.scalar(
                        sa.select(Obj).where(Obj.id == task.get("obj_id"))
                    )
                    if existing_obj is None:
                        log(
                            f"Object {task['obj_id']} not found in the database, skipping"
                        )
                        continue

                    # find the most recent object on TNS within a certain radius (default 2 arcsec) of the object
                    tns_prefix, tns_source = get_IAUname(
                        api_key,
                        tns_headers,
                        ra=existing_obj.ra,
                        dec=existing_obj.dec,
                        radius=float(task.get("radius", DEFAULT_RADIUS)),
                        closest=True,  # get the closest object to the input coordinates as the TNS source
                    )
                    log(
                        f"Found TNS source {tns_source} for object {existing_obj.id} with prefix {tns_prefix}"
                    )
                    if is_null(tns_source):
                        raise ValueError(f"{task.get('obj_id')} not found on TNS.")
                    tns_name = f"{tns_prefix} {tns_source}"
                elif task.get("tns_source"):
                    # a TNS source: name any of our objects within 2 arcsec of it
                    tns_source = task.get("tns_source")
                    tns_prefix = task.get("tns_prefix")

                    # providing the prefix is not mandatory, just nice for logging if we already have it.
                    # we will retrieve it anyway if it's not provided when fetching the object from TNS
                    if tns_prefix:
                        tns_name = f"{tns_prefix} {tns_source}"
                    else:
                        tns_name = tns_source
                    log(f"Processing TNS source {tns_name}")
                else:
                    log("No obj_id or tns_name provided, skipping")
                    continue

                # fetch the data from TNS
                data = {
                    "api_key": api_key,
                    "data": json.dumps(
                        {
                            "objname": tns_source,
                            "photometry": 0,
                            "spectra": 0,
                        }
                    ),
                }

                # 24 * 10 seconds = 4 minutes of retries
                max_retries = 24
                retry_delay = 10
                r = None
                for _ in range(max_retries):
                    r = requests.post(
                        get_tns_url("object"),
                        headers=tns_headers,
                        data=data,
                        allow_redirects=True,
                        stream=True,
                        timeout=10,
                    )
                    status_code = r.status_code
                    if status_code != 429:
                        break
                    time.sleep(retry_delay)

                if status_code != 200:
                    log(f"Error getting TNS data for {tns_name}: {r.text}")
                    continue

                try:
                    tns_source_data = r.json().get("data", {})
                except ValueError:
                    tns_source_data = None
                if tns_source_data is None:
                    log(f"Error getting TNS data for {tns_name}: no reply in data")
                    continue

                try:
                    # '110' is the TNS code we get when an object is not found
                    msg = (
                        tns_source_data.get("name", {})
                        .get("110", {})
                        .get("message", None)
                    )
                    if msg == "No results found.":
                        log(f"Could not find {tns_name} on TNS at {TNS_URL}")
                        continue
                except AttributeError:
                    pass

                tns_prefix = tns_source_data.get("name_prefix", None)
                if tns_prefix is None:
                    log(
                        f"Error processing TNS source {tns_name}: obj has no prefix ({r.json()!s})"
                    )
                    continue

                tns_name = f"{tns_prefix} {tns_source}"

                ra, dec = (
                    tns_source_data.get("radeg", None),
                    tns_source_data.get("decdeg", None),
                )
                if ra is None or dec is None:
                    log(f"Error processing TNS source {tns_name}: no coordinates")
                    continue

                if existing_obj:
                    # if existing obj add TNS name and info to it and update frontend
                    existing_obj.tns_name = tns_name
                    existing_obj.tns_info = tns_source_data
                    session.commit()
                    refresh_obj_on_frontend(existing_obj)
                else:
                    # otherwise, add the TNS name to all the existing sources within a 2 arcsec radius
                    add_tns_name_to_existing_objs(
                        tns_name, tns_source_data, ra, dec, session
                    )

        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            log(f"Error processing TNS source {tns_name}: {e}")
            user_id = task.get("user_id", None)
            if user_id is not None:
                flow = Flow()
                if "not found on TNS" in str(e):
                    flow.push(
                        user_id,
                        action_type="baselayer/SHOW_NOTIFICATION",
                        payload={
                            "note": str(e),
                            "type": "warning",
                        },
                    )
                else:
                    flow.push(
                        user_id,
                        action_type="baselayer/SHOW_NOTIFICATION",
                        payload={
                            "note": f"Error processing TNS source {tns_name}: {e}",
                            "type": "error",
                        },
                    )


def tns_watcher(queue):
    """Watch TNS for new sources and add them to the queue

    Parameters
    ----------
    queue : list
        The queue to add the TNS sources to, shared across threads
    """
    if not TNS_URL or not bot_id or not bot_name or not api_key or not look_back_days:
        log("TNS watcher not configured, skipping")
        return
    tns_headers = get_tns_headers(bot_id, bot_name)

    # when the service starts, we look back a certain number of days
    # useful if the app has been down for a while
    start_date = datetime.now(UTC) - timedelta(days=look_back_days)
    while True:
        try:
            tns_sources = get_recent_TNS(
                api_key,
                tns_headers,
                start_date.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),  # convert start date to isot format
                get_data=False,
            )
            for tns_source in tns_sources:
                queue.append(
                    {
                        "tns_prefix": tns_source["prefix"],
                        "tns_source": tns_source["id"],
                        "obj_id": None,
                    }
                )
                log(f"Added TNS source {tns_source['id']} to the queue for processing")

            # if we got any sources, we update the start date to now - 1 hour
            # otherwise we keep querying TNS starting from same start date
            if tns_sources:
                start_date = datetime.now(UTC) - timedelta(hours=1)
        except Exception as e:  # noqa: BLE001
            log(f"Error getting TNS sources: {e}, retrying in 4 minutes")

        time.sleep(60 * 4)  # sleep for 4 minutes


def api(queue):
    """Start the internal API that endpoint that receives requests from the main app

    Parameters
    ----------
    queue : list
        The queue to add the sources to, shared across threads
    """

    class QueueHandler(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "application/json")
            self.write({"status": "success", "data": {"queue_length": len(queue)}})

        async def post(self):
            try:
                data = tornado.escape.json_decode(self.request.body)
            except json.JSONDecodeError:
                self.set_status(400)
                return self.write({"status": "error", "message": "Malformed JSON data"})

            if "tns_source" in data:
                queue.append({"tns_source": data["tns_source"]})
                self.set_status(200)
                return self.write(
                    {
                        "status": "success",
                        "message": "TNS request accepted into queue",
                        "data": {"queue_length": len(queue)},
                    }
                )

            required_keys = {"obj_id", "user_id"}
            if not required_keys.issubset(set(data.keys())):
                self.set_status(400)
                return self.write(
                    {
                        "status": "error",
                        "message": f"TNS requests requires keys {required_keys}",
                    }
                )

            queue.append(data)

            self.set_status(200)
            return self.write(
                {
                    "status": "success",
                    "message": "TNS request accepted into queue",
                    "data": {"queue_length": len(queue)},
                }
            )

    app = tornado.web.Application([(r"/", QueueHandler)])
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    app.listen(cfg["ports.tns_retrieval_queue"])
    loop.run_forever()


@check_loaded(logger=log)
def service(*args, **kwargs):
    """Process the TNS retrieval queue"""

    queue = []
    t = Thread(target=process_queue, args=(queue,))
    t2 = Thread(target=api, args=(queue,))
    t3 = Thread(target=tns_watcher, args=(queue,))
    t.start()
    t2.start()
    t3.start()
    while True:
        log(f"Current TNS retrieval queue length: {len(queue)}")
        time.sleep(120)
        # Exit if any worker thread died (e.g. DB connection drop in a context
        # manager exit, outside the loop's try/except) so supervisor restarts us.
        if not (t.is_alive() and t2.is_alive() and t3.is_alive()):
            log("A TNS retrieval worker thread died, exiting for supervisor restart")
            sys.exit(1)


if __name__ == "__main__":
    """Start the internal API, the TNS watcher, and the TNS retrieval service"""
    try:
        service()
    except Exception as e:  # noqa: BLE001
        log(f"Error occurred in TNS retrieval queue: {e!s}")
