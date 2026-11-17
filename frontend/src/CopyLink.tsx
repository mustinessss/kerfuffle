import { useState } from "react";

export function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  async function copy() {
    setError("");
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
      setError("Не удалось скопировать. Выделите ссылку и скопируйте её вручную.");
    }
  }

  return (
    <div className="copy-link">
      <code>{url}</code>
      <button className="quiet-button" type="button" onClick={() => void copy()}>
        {copied ? "Скопировано" : "Скопировать ссылку"}
      </button>
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
