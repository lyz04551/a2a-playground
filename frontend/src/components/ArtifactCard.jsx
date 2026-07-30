import React from 'react'

export default function ArtifactCard({ artifact }) {
  return (
    <details className="artifact-card">
      <summary>{artifact.name || artifact.artifact_type || 'Artifact'}</summary>
      <pre>{JSON.stringify(artifact.data || artifact, null, 2)}</pre>
    </details>
  )
}

