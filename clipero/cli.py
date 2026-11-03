"""CLI única: init · setup · doctor · ingest · candidates · transcribe · render · vods · clean · stats · app."""
import argparse
import sys

from . import rutas

SIN_HOME = ("init", "setup", "doctor")   # no exigen una carpeta de trabajo ya creada


def _init(args):
    from .plantilla_init import init
    init(args.dir, args.actualizar)
    return 0


def _setup(args):
    from . import herramientas
    herramientas.setup(args.forzar)
    return 0


def _doctor(args):
    from . import herramientas
    return herramientas.doctor()


def _ingest(args):
    from .ingest import ingest
    ingest(args.url, args.force)
    return 0


def _candidates(args):
    from .score import candidates
    candidates(args.vod_id)
    return 0


def _transcribe(args):
    from .transcribe import transcribe
    transcribe(args.vod_id, [int(n) for n in args.n], args.force)
    return 0


def _render(args):
    from .render import render
    render(args.short)
    return 0


def _vods(args):
    from .sources import vods
    vods(args.dias, args.fuentes.split(",") if args.fuentes else None)
    return 0


def _clean(args):
    from .sources import clean
    clean(args.dias)
    return 0


def _stats(args):
    from .stats import stats
    stats(args.publicados, args.piloto)
    return 0


def _app(args):
    try:
        import uvicorn
        from .app.server import create_app
    except ImportError as e:
        raise RuntimeError(f"falta el extra `app` ({e.name}): pip install \"clipero[app]\"")
    if args.abrir:
        import threading
        import webbrowser
        threading.Timer(1.5, webbrowser.open, args=(f"http://127.0.0.1:{args.port}",)).start()
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipero")
    p.add_argument("--home", default=None, help="carpeta de trabajo (por defecto CLIPERO_HOME, ~/.config/clipero/home o ~/Clipero)")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="crea la carpeta de trabajo con la plantilla (nunca sobrescribe)")
    i.add_argument("dir", nargs="?", default=None, help="por defecto la carpeta de trabajo (~/Clipero)")
    i.add_argument("--actualizar", action="store_true", help="solo reescribe CLAUDE.md, la skill tanda y .clipero/version")
    i.set_defaults(fn=_init)
    se = sub.add_parser("setup", help="baja a .clipero/bin/ lo que falte (ffmpeg, deno, TwitchDownloaderCLI) y precarga Whisper small")
    se.add_argument("--forzar", action="store_true", help="vuelve a bajar aunque ya esté")
    se.set_defaults(fn=_setup)
    dc = sub.add_parser("doctor", help="qué herramientas hay (ruta, versión) y el modo de Claude; código 1 si falta alguna obligatoria")
    dc.set_defaults(fn=_doctor)
    a = sub.add_parser("ingest", help="info + heatmap + chat → data/vods/<id>/")
    a.add_argument("url")
    a.add_argument("--force", action="store_true", help="vuelve a bajar el chat")
    a.set_defaults(fn=_ingest)
    c = sub.add_parser("candidates", help="→ candidatos.json")
    c.add_argument("vod_id")
    c.set_defaults(fn=_candidates)
    t = sub.add_parser("transcribe", help="audio de las ventanas → words.json + candidatos.md")
    t.add_argument("vod_id")
    t.add_argument("n", nargs="*", help="ventanas (sin n = todas)")
    t.add_argument("--force", action="store_true", help="rehace las que ya tienen words.json")
    t.set_defaults(fn=_transcribe)
    r = sub.add_parser("render", help="short.yaml → out/<fecha>/<slug>.mp4 + meta.md")
    r.add_argument("short", help="ruta al short.yaml")
    r.set_defaults(fn=_render)
    v = sub.add_parser("vods", help="VODs recientes de sources.yaml aún sin ingerir (Twitch primero)")
    v.add_argument("--dias", type=int, default=7)
    v.add_argument("--fuentes", default=None, help="ids separados por comas")
    v.set_defaults(fn=_vods)
    cl = sub.add_parser("clean", help="borra data/vods/*/seg/ de más de N días")
    cl.add_argument("--dias", type=int, default=14)
    cl.set_defaults(fn=_clean)
    s_ = sub.add_parser("stats", help="publicados.csv → yt-dlp -j → piloto.csv")
    s_.add_argument("--publicados", default=None, help="por defecto publicados.csv de la carpeta de trabajo")
    s_.add_argument("--piloto", default=None, help="por defecto piloto.csv de la carpeta de trabajo")
    s_.set_defaults(fn=_stats)
    ap = sub.add_parser("app", help="servidor local de la app de escritorio (http://127.0.0.1:8765)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--abrir", action="store_true", help="abre la app en el navegador")
    ap.set_defaults(fn=_app)
    args = p.parse_args(argv)
    rutas.fijar(args.home)   # antes de despachar: ningún módulo calcula rutas al importar
    try:
        if args.cmd not in SIN_HOME and not rutas.version_file().exists():
            raise RuntimeError(f"no hay carpeta de trabajo en {rutas.home()}: ejecuta `clipero init`")
        return args.fn(args)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:   # un binario externo que no está (ffmpeg, ffprobe…)
        print(f"ERROR: no se encuentra `{e.filename}`: ejecuta `clipero setup`", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
