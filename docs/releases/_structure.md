# Release routing

Coordinated package release batches belong here as `release-<n>/index.md`. A batch records independent package versions and refs, scope IDs, entry criteria and exit evidence.

Do not repeat implementation acceptance or open questions here; link to the owning specs. Release-selection questions belong to the release-scope feature. A batch is `shipped` only with tag and installability evidence.

Each unshipped batch records `**Readiness:** ready` or `**Readiness:** not ready`, separately from progress. Its scope/gates table includes progress, spec readiness and release impact for every included epic or feature. Flag any included `not ready` item as a release blocker and link to its spec; an epic-level assignment must expose its unready included features. If only selected features are included, unrelated deferred features do not block the release.

A settled spec marked ready is not evidence that its implementation, validation or approval is complete. Keep those outstanding release gates visible separately. Proposed scope must remain explicitly proposed until selected; not-ready candidate items are conditional blockers, not silently approved scope. Update readiness summaries when their authoritative specs change.
