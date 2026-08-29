"use client";

import { ChangeEvent, DragEvent, useCallback, useRef, useState } from "react";

export default function UploadZone({
  onFiles,
  busy,
}: {
  onFiles: (files: File[]) => void;
  busy: boolean;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length) onFiles(files);
    },
    [onFiles],
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (files.length) onFiles(files);
      e.target.value = "";
    },
    [onFiles],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        dragOver ? "border-accent bg-accent/5" : "border-border hover:border-[#3a4256]"
      }`}
    >
      <input ref={inputRef} type="file" accept="image/*,.pdf" multiple hidden onChange={handleChange} />
      <div className="text-3xl">{busy ? "⏳" : "📤"}</div>
      <p className="text-sm text-[#c7cddb]">
        {busy ? "Analyzing…" : "Drop a photo, screenshot, or PDF here — or click to browse"}
      </p>
      <p className="text-xs text-muted">
        JPEG, PNG, or PDF. Nothing leaves this session — files are analyzed and kept for this demo only.
      </p>
    </div>
  );
}
