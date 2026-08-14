# Alpha Quest Editor v0.9.5-alpha — Relationship Inspector & Display Icons

## Destaques

- **Dependências nos dois sentidos:** a aba Dependências agora mostra quem a quest exige e também quem depende dela.
- **Navegação por relações:** duplo clique em uma quest dependente leva direto ao capítulo/nó correspondente.
- **Checkmark e itens fictícios:** ícones configurados em Tasks, inclusive Checkmark, são lidos e entram no preview/catalogação mesmo quando não representam uma Item Task.
- **Ícones Quest:** novo filtro no catálogo de itens para encontrar ItemStacks usados apenas como elementos visuais do Quest Book.
- **Gameplay x aparência:** o inspetor Geral separa “Item principal / gameplay” de “Ícone visual”.
- Tooltips no canvas mostram pré-requisitos, dependentes e sinalizam ícones com dados/componentes customizados.

## Sobre modelos customizados

O Alpha lê e preserva os ItemStacks e componentes encontrados nos arquivos de quest. Quando a textura/modelo correspondente está disponível em JAR/KubeJS/resource pack, ele tenta usar os assets indexados. Renderizações criadas exclusivamente em runtime por Java/loader podem continuar sem preview 100% fiel; nesses casos o editor mantém a referência e mostra um fallback em vez de esconder o recurso.

## Compatibilidade

Mantém todo o suporte da 0.9.4: scanner universal de JAR/KubeJS, Quest Books SNBT/JSON5, conversão, Lang Splitter, Central de Tradução/QA, edição visual, seleção múltipla, mapa de dependências e build ONEFILE.
