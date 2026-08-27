from baselayer.app.env import load_env

_, cfg = load_env()


def get_app_base_url():
    # This instance runs behind a reverse proxy on the standard port (443/80),
    # so user-facing and callback URLs must not carry the internal server.port.
    return f"{'https' if cfg['server.ssl'] else 'http'}://{cfg['server.host']}"
