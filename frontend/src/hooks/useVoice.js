
import { useState, useRef } from "react";

function useVoice() {
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startListening = async () => {
    try {
      console.log("Starting microphone...");

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      const mediaRecorder = new MediaRecorder(stream);

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.onstart = () => {
        console.log("Microphone started");
        setIsListening(true);
        setTranscript("");
        setReply("");
      };

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        console.log("Microphone stopped");

        setIsListening(false);

        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunksRef.current, {
          type: mediaRecorder.mimeType || "audio/webm",
        });

        await sendAudioToBackend(audioBlob);
      };

      mediaRecorder.start();
    } catch (error) {
      console.error("Microphone error:", error);
      setIsListening(false);
    }
  };

  const stopListening = () => {
    console.log("Stopping microphone...");

    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
    }
  };

  const sendAudioToBackend = async (audioBlob) => {
    try {
      console.log("Sending audio to Solution AI...");

      setIsProcessing(true);

      const arrayBuffer = await audioBlob.arrayBuffer();

      const bytes = new Uint8Array(arrayBuffer);

      let binary = "";

      const chunkSize = 0x8000;

      for (let i = 0; i < bytes.length; i += chunkSize) {
        const chunk = bytes.subarray(i, i + chunkSize);
        binary += String.fromCharCode(...chunk);
      }

      const audioBase64 = btoa(binary);

      const response = await fetch(
        "http://127.0.0.1:8000/api/voice",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            audio_base64: audioBase64,
          }),
        }
      );

      if (!response.ok) {
        const errorText = await response.text();

        throw new Error(
          `Backend error ${response.status}: ${errorText}`
        );
      }

      const data = await response.json();

      console.log("Voice response:", data);

      setTranscript(data.transcript || "");
      setReply(data.reply_text || "");

      if (data.reply_audio_base64) {
  playAudio(
    data.reply_audio_base64,
    data.reply_audio_mime_type || "audio/wav"
  );
}
    } catch (error) {
      console.error("Voice request failed:", error);
      setReply("Sorry, I couldn't process your voice command.");
    } finally {
      setIsProcessing(false);
    }
  };

const playAudio = (
  base64Audio,
  mimeType = "audio/wav"
) => {
    try {
      console.log("Playing Solution AI response...");

      const audio = new Audio(
  `data:${mimeType};base64,${base64Audio}`
);

      audio.play().catch((error) => {
        console.error("Audio playback failed:", error);
      });
    } catch (error) {
      console.error("Could not play response audio:", error);
    }
  };

  const toggleListening = () => {
    if (isProcessing) {
      return;
    }

    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  return {
    isListening,
    isProcessing,
    transcript,
    reply,
    startListening,
    stopListening,
    toggleListening,
  };
}

export default useVoice;
