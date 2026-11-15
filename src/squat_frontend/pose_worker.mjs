// Classic worker keeps importScripts available for the SDK's Wasm loader.
let detector;
self.onmessage = async ({data}) => {
  try {
    if (data.kind === "init") {
      const {FilesetResolver, PoseLandmarker} = await import("./vendor/vision_bundle.mjs");
      const files = await FilesetResolver.forVisionTasks(new URL("./vendor/wasm", self.location.href).href);
      const response = await fetch(new URL("./vendor/pose_landmarker_lite.task", self.location.href));
      if (!response.ok) throw new Error("模型资源读取失败");
      const buffer = await response.arrayBuffer();
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)), b => b.toString(16).padStart(2, "0")).join("");
      if (digest !== data.modelHash) throw new Error("模型SHA256校验失败，请重新运行资源下载脚本");
      detector = await PoseLandmarker.createFromOptions(files, {
        baseOptions: {modelAssetBuffer: new Uint8Array(buffer), delegate: "CPU"},
        runningMode: "VIDEO", numPoses: 2, minPoseDetectionConfidence: .6,
        minPosePresenceConfidence: .6, minTrackingConfidence: .6, outputSegmentationMasks: false
      });
      self.postMessage({kind: "ready", inference_mode: "mediapipe"});
    } else if (data.kind === "frame") {
      try {
        const result = detector.detectForVideo(data.bitmap, data.modelTimeMs);
        self.postMessage({kind: "result", epoch: data.epoch, frameTimeMs: data.frameTimeMs,
          captureWallMs: data.captureWallMs, width: data.width, height: data.height,
          landmarks: result.landmarks});
      } finally { data.bitmap.close(); }
    }
  } catch (error) {
    self.postMessage({kind: "error", message: String(error.message || error)});
  }
};
