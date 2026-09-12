"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { api } from "@/lib/api";

/**
 * Add a site from the dashboard.
 *
 * Worth showing in a demo because of what *doesn't* happen: no retraining, no
 * data upload, no waiting. The models predict capacity factor from weather, so
 * a new site anywhere on earth starts forecasting on its next refresh with
 * nothing but a name, a coordinate and a nameplate rating.
 */
export function AddSiteDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    site_type: "solar",
    latitude: "",
    longitude: "",
    capacity_kw: "",
    region: "",
    storage_capacity_kwh: "",
  });

  const update = (key: string, value: string) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createSite({
        name: form.name.trim(),
        site_type: form.site_type,
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        capacity_kw: Number(form.capacity_kw),
        region: form.region.trim(),
        storage_capacity_kwh: Number(form.storage_capacity_kwh || 0),
        storage_soc_kwh: Number(form.storage_capacity_kwh || 0) * 0.4,
      });
      setOpen(false);
      setForm({
        name: "",
        site_type: "solar",
        latitude: "",
        longitude: "",
        capacity_kw: "",
        region: "",
        storage_capacity_kwh: "",
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-xl border border-solar/25 bg-solar/10 px-3.5 py-2 text-sm font-medium text-solar transition-colors hover:bg-solar/15"
      >
        <PlusIcon /> Add site
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[1000] grid place-items-center bg-base-900/80 p-4 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <motion.form
              initial={{ opacity: 0, y: 18, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.98 }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              onClick={(event) => event.stopPropagation()}
              onSubmit={submit}
              className="glass w-full max-w-lg space-y-4 p-6"
            >
              <div>
                <h2 className="text-lg font-semibold text-white">Add a site</h2>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                  It starts forecasting on the next refresh — the models work from weather and
                  capacity factor, so there is nothing to retrain.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Site name" className="sm:col-span-2">
                  <input
                    required
                    value={form.name}
                    onChange={(event) => update("name", event.target.value)}
                    placeholder="Kutch Solar Park"
                    className={inputClass}
                  />
                </Field>

                <Field label="Technology">
                  <select
                    value={form.site_type}
                    onChange={(event) => update("site_type", event.target.value)}
                    className={inputClass}
                  >
                    <option value="solar">Solar PV</option>
                    <option value="wind">Wind</option>
                  </select>
                </Field>

                <Field label="Nameplate (kW)">
                  <input
                    required
                    type="number"
                    min={1}
                    value={form.capacity_kw}
                    onChange={(event) => update("capacity_kw", event.target.value)}
                    placeholder="50000"
                    className={inputClass}
                  />
                </Field>

                <Field label="Latitude">
                  <input
                    required
                    type="number"
                    step="0.0001"
                    min={-90}
                    max={90}
                    value={form.latitude}
                    onChange={(event) => update("latitude", event.target.value)}
                    placeholder="23.24"
                    className={inputClass}
                  />
                </Field>

                <Field label="Longitude">
                  <input
                    required
                    type="number"
                    step="0.0001"
                    min={-180}
                    max={180}
                    value={form.longitude}
                    onChange={(event) => update("longitude", event.target.value)}
                    placeholder="69.67"
                    className={inputClass}
                  />
                </Field>

                <Field label="Region">
                  <input
                    value={form.region}
                    onChange={(event) => update("region", event.target.value)}
                    placeholder="Gujarat, India"
                    className={inputClass}
                  />
                </Field>

                <Field label="Storage (kWh, optional)">
                  <input
                    type="number"
                    min={0}
                    value={form.storage_capacity_kwh}
                    onChange={(event) => update("storage_capacity_kwh", event.target.value)}
                    placeholder="0"
                    className={inputClass}
                  />
                </Field>
              </div>

              {error && (
                <p className="rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-xs text-danger">
                  {error}
                </p>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-3.5 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-lg bg-solar/90 px-4 py-2 text-sm font-medium text-base-900 transition-colors hover:bg-solar disabled:opacity-50"
                >
                  {submitting ? "Adding…" : "Add site"}
                </button>
              </div>
            </motion.form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

const inputClass =
  "w-full rounded-lg border border-white/10 bg-base-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-solar/50";

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}
