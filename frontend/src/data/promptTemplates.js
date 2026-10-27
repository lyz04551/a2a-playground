// Starter tasks come from the currently registered Agent cards.
export function agentPromptTemplates(agents = [], language = 'en-US') {
  return agents.flatMap(agent => (agent.skills || []).flatMap(skill =>
    (skill.examples || []).filter(example => typeof example === 'string' && example.trim()).map((example, index) => ({
      id: `${agent.id}:${skill.id}:${index}`,
      title: skill.name || agent.name || agent.id,
      description: agent.name || agent.id,
      prompt: language === 'zh-CN' ? `请用中文回答：${example.trim()}` : example.trim(),
    })),
  ))
}
