# make tools: YuNet (va en git y en el wheel; esto solo lo rebaja si falta) y `clipero setup` (ffmpeg, deno, TwitchDownloaderCLI y Whisper small en $CLIPERO_HOME/.clipero/)
YUNET_URL := https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
YUNET := clipero/recursos/models/face_detection_yunet_2023mar.onnx

.PHONY: tools app instalar-app
tools: $(YUNET)
	.venv/bin/clipero setup

$(YUNET):
	mkdir -p clipero/recursos/models
	curl -fL -o $(YUNET).part $(YUNET_URL)
	mv $(YUNET).part $(YUNET)

# make app: compila el frontend (→ clipero/app/static). make instalar-app: instala y arranca el servicio y el lanzador
app:
	cd web && npm ci && npm run build

instalar-app:
	bash deploy/instalar.sh
