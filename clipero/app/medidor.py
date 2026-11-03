"""Medidor: stats.stats() en un hilo, al arrancar y cada 6 h si hoy no se ha medido, y a demanda."""
import asyncio
from datetime import date
from pathlib import Path

from .. import stats

INTERVALO_S = 6 * 3600


def _log(msg):
    print(f"medidor: {msg}", flush=True)   # llega al journal


class Medidor:
    def __init__(self, root, fetch=None, hoy=None, intervalo=INTERVALO_S, ocupado=lambda: False):
        self.root = Path(root)
        self.fetch = fetch or stats.fetch_metrics
        self.hoy = hoy or (lambda: date.today().isoformat())
        self.intervalo = intervalo
        self.ocupado = ocupado
        self.lock = asyncio.Lock()
        self.midiendo = False
        self.error = None
        self.ultima = self._ultima_csv()
        self._tarea = None

    def _filas(self):
        return stats._leer(self.root / "piloto.csv")

    def _ultima_csv(self):
        return max((r["fecha_medida"] for r in self._filas() if r.get("fecha_medida")), default=None)

    def estado(self):
        return {"midiendo": self.midiendo, "ultima": self.ultima, "error": self.error}

    def iniciar(self) -> bool:
        """Lanza una medición forzada en segundo plano. False si ya hay una en curso."""
        if self.midiendo:
            return False
        self.midiendo = True   # síncrono: un segundo POST ve ya el 409
        self._tarea = asyncio.create_task(self._medir())
        return True

    async def _medir(self):
        async with self.lock:
            self.midiendo, self.error = True, None
            _log("mide")
            try:
                await asyncio.to_thread(stats.stats, self.root / "publicados.csv", self.root / "piloto.csv",
                                        self.hoy(), self.fetch)
            except Exception as e:  # noqa: BLE001 — se muestra en la UI, no tumba el servidor
                self.error = str(e) or e.__class__.__name__
                _log(f"error: {self.error}")
            finally:
                self.ultima = self._ultima_csv()
                self.midiendo = False

    async def medir_si_toca(self):
        if self.ocupado():
            _log("no mide: hay una sesión en curso")
            return False
        hoy = self.hoy()
        if any(r.get("fecha_medida") == hoy for r in self._filas()):
            _log(f"no mide: ya hay filas de hoy ({hoy})")
            return False
        return self.iniciar()

    async def bucle(self):
        while True:
            try:
                await self.medir_si_toca()
            except Exception as e:  # noqa: BLE001
                _log(f"error: {e}")
            await asyncio.sleep(self.intervalo)
