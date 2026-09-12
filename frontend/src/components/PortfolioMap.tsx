"use client";

import "leaflet/dist/leaflet.css";

import type { LatLngBoundsExpression, LatLngTuple } from "leaflet";
import { useRouter } from "next/navigation";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";

import { mw, pct } from "@/lib/format";
import type { PortfolioSite, SiteStatus } from "@/lib/types";

const STATUS_COLOR: Record<SiteStatus, string> = {
  critical: "#f87171",
  warning: "#fbbf24",
  normal: "#34d399",
  unavailable: "#64748b",
};

/**
 * Portfolio map. Loaded through a dynamic import with SSR off (see the parent):
 * Leaflet reaches straight for `window` at module scope, so rendering it on the
 * server throws before the page ever gets to the browser.
 *
 * Marker radius scales with nameplate so a 240 MW offshore array reads as
 * bigger than a 92 MW solar farm without needing a legend, and colour carries
 * alert status. The dark tile filter lives in globals.css.
 */
export function PortfolioMap({ sites }: { sites: PortfolioSite[] }) {
  const router = useRouter();
  const maxCapacity = Math.max(...sites.map((site) => site.capacity_kw), 1);

  // Frame the map around whatever sites actually exist rather than a fixed
  // world view -- the seeded portfolio spans Chile to India, and a user who
  // adds two sites in one country should get a regional view, not a globe.
  const bounds: LatLngBoundsExpression | undefined =
    sites.length > 1
      ? (sites.map((site) => [site.latitude, site.longitude] as LatLngTuple) as LatLngBoundsExpression)
      : undefined;
  const center: LatLngTuple = sites.length === 1
    ? [sites[0].latitude, sites[0].longitude]
    : [22, 12];

  return (
    <MapContainer
      bounds={bounds}
      boundsOptions={{ padding: [44, 44] }}
      center={bounds ? undefined : center}
      zoom={bounds ? undefined : 5}
      minZoom={1}
      maxZoom={9}
      scrollWheelZoom={false}
      worldCopyJump
      style={{ height: "100%", width: "100%", borderRadius: "1rem" }}
      attributionControl
    >
      {/* Plain OpenStreetMap tiles: genuinely keyless, which keeps the "runs
          from a clean clone with no accounts" promise intact. They ship light,
          so globals.css inverts them into the dark theme. */}
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
      />

      {sites.map((site) => {
        const color = STATUS_COLOR[site.status];
        // sqrt keeps the *area* proportional to capacity, which is how people
        // actually read circle size.
        const radius = 7 + Math.sqrt(site.capacity_kw / maxCapacity) * 11;

        return (
          <CircleMarker
            key={site.id}
            center={[site.latitude, site.longitude]}
            radius={radius}
            pathOptions={{
              color,
              weight: 2,
              fillColor: color,
              fillOpacity: site.status === "normal" ? 0.24 : 0.42,
            }}
            eventHandlers={{ click: () => router.push(`/sites/${site.id}`) }}
          >
            <Tooltip direction="top" offset={[0, -6]} opacity={1}>
              <div className="min-w-[190px] space-y-1 p-0.5 text-[12px]">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-900">{site.name}</span>
                  <span
                    className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                    style={{ background: `${color}26`, color: "#0f172a" }}
                  >
                    {site.site_type}
                  </span>
                </div>
                <div className="text-slate-600">{site.region}</div>
                <div className="flex justify-between gap-4 text-slate-700">
                  <span>Now</span>
                  <span className="font-mono">
                    {mw(site.current_output_kw)} ({pct(site.capacity_factor)})
                  </span>
                </div>
                <div className="flex justify-between gap-4 text-slate-700">
                  <span>Nameplate</span>
                  <span className="font-mono">{mw(site.capacity_kw, 0)}</span>
                </div>
                {site.alert_counts.critical + site.alert_counts.warning > 0 && (
                  <div className="text-slate-700">
                    {site.alert_counts.critical} critical · {site.alert_counts.warning} warning
                  </div>
                )}
                <div className="pt-0.5 text-[11px] italic text-slate-500">Click to open site</div>
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
