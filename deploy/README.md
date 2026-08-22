# Deploying turboportal on the CSE VM (cse-skyportal-prd-web-01)

Fresh, public-facing SkyPortal. Persistent data is on the NFS mount; the app runs
in Docker under systemd; config is in git. See the wiki page
"Setting up TurboPortal on the CSE VM" for the full host prep (LVs, NFS mount,
Docker install). This file is the repo-local runbook.

## Prereqs on the host (one-time, see wiki)
- NFS mounted at /mnt/rds (vers=3,hard,noatime,local_lock=all).
- LVs: /local (code), /var/lib/docker. Docker installed.
- NFS data dirs owned by the container uids:
    sudo mkdir -p /mnt/rds/turboportal/{db,thumbnails,persistentdata}
    sudo chown -R 999:999   /mnt/rds/turboportal/db
    sudo chown -R 1000:1000 /mnt/rds/turboportal/thumbnails /mnt/rds/turboportal/persistentdata

## Secrets (run as root so it is not tied to a personal home)
The age identity is the shared `turbo` ssh key. Put it at /root/.ssh/turbo and run
setup_secrets as root; this decrypts config/docker.yaml and installs the
pre-commit(re-encrypt)/post-merge(re-decrypt) hooks.

    sudo install -m 600 <turbo key> /root/.ssh/turbo
    sudo scripts/setup_secrets.sh          # uses $HOME=/root -> /root/.ssh/turbo

For a fresh node, edit config/docker.yaml before first use: new secret_key
(base64.b64encode(os.urandom(50))), server.host = this node's public name, add the
new host's Google OAuth redirect URI (and http://localhost:8000/... for the SSH
tunnel view). Committing re-encrypts it to config/docker.yaml.age via the hook.

Note: db-init reads a root `config.yaml`; keep it consistent with config/docker.yaml
(setup_secrets/deploy creates it). Confirm at first bring-up from the logs.

## Bring up (view over SSH tunnel first, nothing public)
    cd /local/turbo && sudo git pull
    sudo docker compose up -d --build
    sudo docker compose ps
    sudo docker compose logs -f db-init web
    # once web is healthy:
    sudo docker compose exec web bash -lc 'source .venv/bin/activate && make load_seed_data'
    sudo docker compose exec web bash -lc 'source .venv/bin/activate && PYTHONPATH=. python tools/data_loader.py data/turbo_seed.yaml --config=/etc/skyportal/docker.yaml'

View from your laptop (no public exposure):
    ssh -L 8000:127.0.0.1:8000 <you>@cse-skyportal-prd-web-01   # browse http://localhost:8000

## Run under systemd (lifecycle not tied to a login)
    sudo cp deploy/turboportal.service /etc/systemd/system/
    sudo systemctl daemon-reload && sudo systemctl enable --now turboportal
    # manage: sudo systemctl {start,stop,restart} turboportal

## Poster integration (skyportal_poster.service on migizi)
The poster posts to SkyPortal's API with a token that must be exempt from the
per-token /api rate limit (baselayer services/nginx/nginx.conf.template). That edit
lives in the baselayer submodule and does NOT come from a clone. On this node:
  1. create the poster's API token in this DB (properly scoped),
  2. add that token to the rate-limit exemption in baselayer's nginx.conf.template,
  3. repoint migizi's skyportal_poster.service to this node's URL + the new token.

## Public exposure (later)
Cloudflare Tunnel under the shared turbotelescopeteam account; cloudflared connects
to 127.0.0.1:8000. Keep the web ports bound to localhost (already set in compose).
