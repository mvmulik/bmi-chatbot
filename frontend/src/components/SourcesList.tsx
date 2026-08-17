import type { ChatSource } from '../types/chat'

type SourcesListProps = {
  sources: ChatSource[]
}

export function SourcesList({ sources }: SourcesListProps) {
  if (!sources.length) {
    return null
  }

  return (
    <div className="sources">
      <p className="sources-label">Sources</p>
      <ul>
        {sources.map((source, index) => (
          <li key={`${source.url}-${source.section}-${index}`}>
            <div className="source-title">{source.title || 'BMI Hub page'}</div>
            {source.section ? <div className="source-section">{source.section}</div> : null}
            {source.url ? (
              <a href={source.url} target="_blank" rel="noreferrer noopener">
                {source.url}
              </a>
            ) : (
              <span className="source-missing">URL unavailable</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
