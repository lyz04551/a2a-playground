import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { normalizeMarkdown } from '../state/markdown'

export default function MarkdownContent({ children, compact = false, interactiveLinks = true }) {
  return <div className={`markdown-content${compact ? ' is-compact' : ''}`}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children: tableChildren }) => <div className="markdown-content__table"><table>{tableChildren}</table></div>,
        a: ({ children: linkChildren, href }) => interactiveLinks
          ? <a href={href} target="_blank" rel="noreferrer noopener">{linkChildren}</a>
          : <span>{linkChildren}</span>,
      }}
    >{normalizeMarkdown(children)}</ReactMarkdown>
  </div>
}
