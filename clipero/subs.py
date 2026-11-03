"""subs: words.json (palabras con tiempos del VOD) → ASS palabra a palabra.

Grupos de 2–3 palabras en mayúsculas; la palabra en curso en amarillo (`&H00FFFF&`) y el resto en blanco
con borde negro de 6 px, Montserrat ExtraBold 78 px. Posición: franja central (y=960) con layout,
70 % de la altura (y=1344) sin él; con escenas, y=1480 (bajo la franja 16:9).

Dos reglas que salieron del M0 (`data/spike/build.py`): se quitan las palabras que cruzan el borde de un
tramo, y el final de cada evento se recorta al inicio del siguiente, para que nunca se solapen.
"""
import re

Y_LAYOUT = 960      # centro de la franja 810–1110
Y_SIN_LAYOUT = 1344  # 70 % de 1920
Y_ESCENAS = 1480     # debajo de la franja 16:9 de las escenas (y 690–1298): no tapa ninguna cara
MAX_CHARS = 20       # por grupo, para no pasar a dos líneas con 78 px
TAIL = 0.25          # lo que se alarga la última palabra de un grupo si hay hueco
PAUSE = 0.7          # una pausa mayor corta el grupo
EDGE = 0.02          # tolerancia al borde de un tramo
MIN_DUR = 0.03

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Sub,Montserrat ExtraBold,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,6,0,5,70,70,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def clean(w):
    """Palabra → texto de subtítulo: mayúsculas, sin puntuación ni caracteres que el ASS interpreta."""
    return re.sub(r"[.,;:¿?¡!…\"«»()\[\]{}\\]", "", w).strip().upper()


def tramo_words(words, a, b):
    """Palabras que caen enteras dentro de [a, b] (las que cruzan el borde se quitan), con texto limpio."""
    out = []
    for w in words:
        if w["s"] >= a - EDGE and w["e"] <= b + EDGE:
            t = clean(w["w"])
            if t:
                out.append({"w": t, "raw": w["w"], "s": max(w["s"], a), "e": min(w["e"], b)})
    return out


def group_words(ws):
    """Palabras → grupos de 2–3 (solo 1 si la frase tiene una sola palabra o la palabra es larguísima).
    Corta en fin de frase (`. ? !`) o en una pausa > PAUSE."""
    sentences, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        pausa = i + 1 < len(ws) and ws[i + 1]["s"] - w["e"] > PAUSE
        if re.search(r"[.?!…]$", w["raw"].strip()) or pausa:
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    groups = []
    for sen in sentences:
        g = []
        for w in sen:
            nchars = sum(len(x["w"]) for x in g) + len(g) + len(w["w"])
            if g and (len(g) == 3 or nchars > MAX_CHARS):
                groups.append(g)
                g = []
            g.append(w)
        if g:
            groups.append(g)
        # (3,1) → (2,2) dentro de la misma frase
        if len(groups) >= 2 and len(groups[-1]) == 1 and len(groups[-2]) == 3 and groups[-2][-1] in sen:
            last = groups[-2].pop()
            groups[-1].insert(0, last)
    return groups


def tramo_events(words, a, b, t0, y):
    """Eventos [(inicio, fin, texto_ass, y)] en tiempo del short para un tramo [a, b] del VOD que
    empieza en t0 del short. Un evento por palabra: el grupo entero con esa palabra en amarillo."""
    ws = tramo_words(words, a, b)
    groups = group_words(ws)
    end_tramo = t0 + (b - a)
    ev = []
    for gi, g in enumerate(groups):
        nxt = t0 + groups[gi + 1][0]["s"] - a if gi + 1 < len(groups) else end_tramo
        txt = [w["w"] for w in g]
        for k, w in enumerate(g):
            s = t0 + w["s"] - a
            e = (t0 + g[k + 1]["s"] - a) if k + 1 < len(g) else min(t0 + w["e"] - a + TAIL, nxt)
            e = min(e, end_tramo)
            parts = [("{\\c&H00FFFF&}" if j == k else "{\\c&HFFFFFF&}") + txt[j] for j in range(len(g))]
            ev.append((s, e, " ".join(parts), y))
    return ev


def ts(t):
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def build_ass(events):
    """Eventos (de todos los tramos) → texto ASS sin solapes: se ordenan, se pasa a centésimas y el
    final de cada uno se recorta al inicio del siguiente."""
    evs = sorted(([round(s * 100), round(e * 100), t, y] for s, e, t, y in events), key=lambda x: x[0])
    for i in range(len(evs) - 1):
        evs[i][1] = min(evs[i][1], evs[i + 1][0])
    lines = []
    for s, e, t, y in evs:
        if e - s < MIN_DUR * 100 * 0.5:
            continue
        lines.append(f"Dialogue: 0,{ts(s / 100)},{ts(e / 100)},Sub,,0,0,0,,{{\\an5\\pos(540,{y})}}{t}")
    return HEADER + "\n".join(lines) + "\n"


def parse_dialogues(ass):
    """ASS → [(inicio, fin, [palabras], palabra_en_amarillo)] (para los tests)."""
    out = []
    for ln in ass.splitlines():
        if not ln.startswith("Dialogue:"):
            continue
        f = ln.split(",", 9)
        h = lambda x: sum(float(p) * m for p, m in zip(x.split(":"), (3600, 60, 1)))
        body = f[9].split("}", 1)[1]
        toks = re.findall(r"\{\\c&H([0-9A-F]{6})&\}([^{]*)", body)
        words = [t.strip() for _, t in toks]
        cur = next((t.strip() for c, t in toks if c == "00FFFF"), None)
        out.append((h(f[1]), h(f[2]), words, cur))
    return out
