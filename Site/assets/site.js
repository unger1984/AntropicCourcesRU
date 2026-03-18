document.addEventListener("DOMContentLoaded", () => {
  const wrappers = document.querySelectorAll("[data-player-root]");
  for (const wrapper of wrappers) {
    const video = wrapper.querySelector("video");
    if (!video) {
      continue;
    }
    const toolbarScope = wrapper.closest(".video-max") || wrapper;

    const embeddedTrackPayload = wrapper.querySelector("[data-subtitles-json]");
    if (embeddedTrackPayload && window.VTTCue) {
      try {
        const subtitles = JSON.parse(embeddedTrackPayload.textContent || "{}");
        for (const [language, config] of Object.entries(subtitles)) {
          const track = video.addTextTrack("subtitles", config.label || language, language);
          track.mode = "hidden";
          for (const cue of config.cues || []) {
            track.addCue(new VTTCue(cue.start, cue.end, cue.text));
          }
        }
      } catch (error) {
        console.error("Failed to initialize embedded subtitles", error);
      }
    }

    const setSubtitle = (language) => {
      const tracks = Array.from(video.textTracks || []);
      for (const track of tracks) {
        track.mode = language !== "off" && track.language === language ? "showing" : "hidden";
      }
      for (const button of toolbarScope.querySelectorAll("[data-subtitle]")) {
        button.classList.toggle("is-active", button.dataset.subtitle === language);
      }
    };

    const setAudio = (audioKey) => {
      const source = wrapper.querySelector(`source[data-audio="${audioKey}"]`);
      if (!source || video.dataset.activeAudio === audioKey) {
        return;
      }
      const currentTime = video.currentTime || 0;
      const wasPaused = video.paused;
      video.dataset.activeAudio = audioKey;
      video.src = source.src;
      video.load();
      video.addEventListener(
        "loadedmetadata",
        () => {
          video.currentTime = Math.min(currentTime, Math.max((video.duration || currentTime) - 0.25, 0));
          if (!wasPaused) {
            video.play().catch(() => {});
          }
        },
        { once: true }
      );
      for (const button of toolbarScope.querySelectorAll("[data-audio-option]")) {
        button.classList.toggle("is-active", button.dataset.audioOption === audioKey);
      }
    };

    for (const button of toolbarScope.querySelectorAll("[data-subtitle]")) {
      button.addEventListener("click", () => {
        setSubtitle(button.dataset.subtitle || "off");
      });
    }

    for (const button of toolbarScope.querySelectorAll("[data-audio-option]")) {
      button.addEventListener("click", () => {
        setAudio(button.dataset.audioOption || "original");
      });
    }

    setSubtitle(wrapper.dataset.defaultSubtitle || "off");
    setAudio(wrapper.dataset.defaultAudio || "ru");
  }
});
