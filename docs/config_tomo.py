lport = 5678
guis = [("mamba.attitude.capi_frontend", ("atti_tomo",), "Main")]

def server_init(globals, config):
    from mamba_site.init import init
    init(globals, config)

def client_build(config):
    from mamba.backend.mzserver import client_build_base
    from mamba.backend.addon_core import cextend_core
    mrc = cextend_core(client_build_base(config))
    return mrc, mrc.znc

