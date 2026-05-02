import type { PublicationMethodologyProfile } from "@/lib/methodologyProfiles";

function profileKindLabel(patternType: string): string {
  return patternType.replace(/_/g, " ");
}

function clippedList(items: string[]): string[] {
  return items.slice(0, 3);
}

function MethodologyDetail({
  label,
  values,
}: {
  label: string;
  values: string[];
}) {
  if (values.length === 0) return null;

  return (
    <div className="transcript-methodology-detail">
      <dt className="mono">{label}</dt>
      <dd>{clippedList(values).join("; ")}</dd>
    </div>
  );
}

export default function MethodologyProfilesPanel({
  profiles,
}: {
  profiles: PublicationMethodologyProfile[];
}) {
  return (
    <section className="portal-card transcript-methodology-panel" aria-labelledby="transcript-methodology-title">
      <div className="transcript-methodology-head">
        <div>
          <h2 className="mono" id="transcript-methodology-title">
            Methodology profiles
          </h2>
          <p>Reasoning methods extracted from this source, separated from speaker identity and conclusions.</p>
        </div>
        <span className="mono">{profiles.length} frame{profiles.length === 1 ? "" : "s"}</span>
      </div>

      {profiles.length ? (
        <ol className="transcript-methodology-list">
          {profiles.map((profile) => (
            <li className="transcript-methodology-card" key={`${profile.patternType}-${profile.title}`}>
              <div className="transcript-methodology-card-head">
                <span className="mono">{profileKindLabel(profile.patternType)}</span>
                <span className="mono">{(profile.confidence * 100).toFixed(0)}%</span>
              </div>
              <h3>{profile.title}</h3>
              <p className="transcript-methodology-summary">{profile.summary}</p>
              <dl className="transcript-methodology-details">
                <MethodologyDetail label="Moves" values={profile.reasoningMoves} />
                <MethodologyDetail label="Assumptions" values={profile.assumptions} />
                <MethodologyDetail label="Transfers" values={profile.transferTargets} />
                <MethodologyDetail label="Risks" values={profile.failureModes} />
              </dl>
            </li>
          ))}
        </ol>
      ) : (
        <div className="transcript-methodology-empty">
          <strong>No methodology profiles yet.</strong>
          <p>
            Re-run Noosphere ingestion or the methodology reanalysis script after the database migration is applied.
          </p>
        </div>
      )}
    </section>
  );
}
