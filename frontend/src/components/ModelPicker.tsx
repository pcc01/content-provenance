import { useEffect, useState } from "react";
import { api, MODEL_DISCOVERABLE_PROVIDERS } from "../api/client";

// Phase 18 — "select the LLM system and then the model within it," read
// live from the system rather than a hardcoded guess. Every provider with
// more than one selectable model (the three local multi-model servers,
// plus Claude/OpenAI/Gemini which each ship multiple generations/sizes)
// gets a second dropdown that only appears once a provider offering one is
// picked, populated from GET /api/v1/models/{provider}. Pure single-model
// NMT services (DeepL, Google Translate, MS Translator) never show one.
interface Props {
  providers: { value: string; label: string }[]; // TRANSLATE_PROVIDERS or EVALUATE_PROVIDERS
  provider: string;
  model: string;
  onProviderChange: (p: string) => void;
  onModelChange: (m: string) => void;
  label: string; // "Translate with" / "Evaluate with" / "Retranslate with"
}

export function ModelPicker({ providers, provider, model, onProviderChange, onModelChange, label }: Props) {
  const [models, setModels] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const discoverable = provider !== "" && MODEL_DISCOVERABLE_PROVIDERS.has(provider);

  useEffect(() => {
    setModels(null);
    setError(null);
    onModelChange(""); // a model from the previous provider isn't valid here
    if (!discoverable) return;
    setLoading(true);
    api.getModels(provider)
      .then((r) => setModels(r.models))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    // Only re-run when the provider itself changes — onModelChange is a
    // fresh function reference every parent render and would otherwise
    // loop this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, discoverable]);

  return (
    <div style={{ display: "flex", gap: 8 }}>
      <label style={{ fontSize: 13 }}>
        {label}
        <select value={provider} onChange={(e) => onProviderChange(e.target.value)}
                style={{ display: "block", padding: 4, marginTop: 4, minWidth: 190 }}>
          {providers.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </label>
      {discoverable && (
        <label style={{ fontSize: 13 }}>
          Model
          <select
            value={model} onChange={(e) => onModelChange(e.target.value)}
            disabled={loading || !!error || (models?.length ?? 0) === 0}
            style={{ display: "block", padding: 4, marginTop: 4, minWidth: 220 }}
          >
            <option value="">{loading ? "Loading…" : "Default"}</option>
            {models?.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          {error && (
            <div style={{ fontSize: 11, color: "#b91c1c", marginTop: 2, maxWidth: 220 }}>
              Couldn't list models ({error}) — will use the configured default.
            </div>
          )}
          {models && models.length === 0 && !error && (
            <div style={{ fontSize: 11, color: "#92400e", marginTop: 2, maxWidth: 220 }}>
              No models found on that server.
            </div>
          )}
        </label>
      )}
    </div>
  );
}
