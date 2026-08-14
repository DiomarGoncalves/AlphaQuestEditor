# Changelog

## 0.9.5-alpha — Relationship Inspector & Display Icons

### Dependências nos dois sentidos
- A aba **Dependências** agora mostra separadamente **Pré-requisitos — esta quest depende de** e **Dependentes — quests que precisam desta**.
- Resumo visual `N pré-requisitos → quest atual → M dependentes`.
- Pesquisa independente nos dois lados por nome ou ID.
- Duplo clique em um dependente abre diretamente essa quest no canvas, inclusive quando está em outro capítulo.
- O núcleo mantém um índice reverso de dependências após cada carregamento, evitando rescans completos ao selecionar quests.
- Tooltips dos nós no canvas mostram contagem/IDs de pré-requisitos e dependentes.

### Checkmark, ícones decorativos e itens fictícios
- Tasks agora preservam e indexam `icon` mesmo quando não são Item Tasks, incluindo **checkmark** e tasks customizadas.
- O preview da quest passa a considerar: ícone explícito da quest → ícone explícito de task → item da Item Task.
- Checkmarks sem textura resolvida recebem fallback visual `✓` em vez de um `?` genérico.
- ItemStacks usados apenas como ícones de quest/task/grupo/capítulo entram no catálogo como **Ícones Quest**, mesmo se não aparecerem no registry detectado.
- Nova opção **Ícones Quest** no filtro da lista de itens.
- O editor sinaliza quando um ícone possui `components`, `custom_model_data`/`CustomModelData` ou `minecraft:item_model`; quando o modelo exato não puder ser reproduzido offline, o ID e os dados continuam preservados.
- A aba Geral diferencia **Item principal / gameplay** de **Ícone visual**, evitando confundir um checkmark decorativo com um objetivo de item.

## 0.9.4-alpha — Universal Assets & KubeJS

### Compatibilidade por versão
- Scanner de itens/assets desacoplado de versões fixas do Minecraft.
- Detecção automática de versão por manifestos CurseForge/Prism/MultiMC quando disponíveis.
- Em versão desconhecida o scanner continua em modo Auto e não injeta um catálogo vanilla incorreto.
- Suporte heurístico a layouts antigos e modernos de assets de itens.

### Biblioteca de Assets
- Nova ferramenta **Assets** na navbar, utilizável sem abrir modpack/Quest Book.
- Importação de JARs individuais, pasta inteira de JARs e pasta KubeJS independente.
- Visualização pesquisável de itens e imagens/resource locations.
- PNGs de qualquer pasta `assets/<namespace>/...` podem ser visualizados e copiados pelo ID.

### KubeJS Scanner
- Leitura de `kubejs/assets` para texturas, modelos, idiomas e imagens de quests.
- Detecção de itens customizados em sintaxe moderna `StartupEvents.registry('item', ...)`.
- Compatibilidade heurística com sintaxe legacy `item.registry`/`onEvent`.
- IDs sem namespace são normalizados para `kubejs:<id>`.
- Leitura de `.displayName()`, `.texture()`/`.textureAll()` e referências `Item.of()`.
- KubeJS continua sendo apenas analisado; scripts não são executados pelo Alpha Quest Editor.

## 0.9.3-alpha — Translation Sync & QA

### Central de Tradução
- Nova ferramenta **Tradução** na navbar e botão **Central de Tradução** na aba de idiomas.
- Importação direta de arquivos `.snbt`, `.json5` e `.json` atualizados, sem exigir que o tradutor conheça a estrutura física do Quest Book.
- Detecção automática de locale pelo nome/caminho do arquivo, com seleção manual de destino e idioma de origem para QA.
- Prévia linha a linha com status **ALTERADA**, **NOVA**, **IGUAL** e **CHAVE_DESCONHECIDA**.
- Apenas alterações seguras são marcadas automaticamente; chaves desconhecidas exigem escolha explícita.
- Aplicação usa o roteador interno de idiomas para salvar cada chave no arquivo correto em SNBT flat, SNBT split ou JSON5 split.
- Importação inteira entra como uma única operação de histórico e pode ser revertida com `Ctrl+Z`.

### QA de tradução
- Erros de sintaxe exibem linha e coluna exatas.
- Detecção de string fisicamente quebrada em outra linha, string não fechada e chave duplicada.
- Detecção de chaves que não existem no Quest Book, com sugestão de chave semelhante para encontrar IDs/dígitos digitados incorretamente.
- Comparação com o idioma de origem para placeholders/códigos (`%s`, `{name}`, `§a`), números/percentuais, tags e quantidade de quebras de linha.
- Aba **QA do projeto** valida todos os arquivos físicos do locale atual e informa arquivo + linha + chave + problema.

## 0.9.2-alpha — Dependency Mapper

### Mapa de Dependências
- Nova ferramenta **Deps em lote** exposta diretamente na navbar, ao lado de Tema.
- Fluxo em dois lados: **Dependências (pré-requisitos)** → **Quem recebe (dependentes/codependências)**.
- Cada lado pode ser capturado diretamente da seleção atual do canvas, permitindo selecionar, capturar, trocar a seleção e capturar o outro lado sem fechar a ferramenta.
- Suporte N→M: 4 pré-requisitos podem ser aplicados a 1 quest final, 1 pré-requisito pode alimentar 10 quests ou vários pré-requisitos podem ser ligados a várias quests em uma única operação.
- Modo **Adicionar sem substituir** preserva dependências já existentes.
- Modo **Remover esta relação** remove somente as relações escolhidas.
- Prévia mostra quantas dependências, quantas quests dependentes e quantas relações serão processadas.
- Bloqueio de auto-dependência quando a mesma quest aparece nos dois lados.
- Botão para trocar os dois lados da relação.
- Toda aplicação entra como uma única operação no histórico e pode ser desfeita com `Ctrl+Z`.

## 0.9.1-alpha — Editor Toolbar & Compact Navbar

### Navbar em uma linha
- Removido o status largo do projeto da toolbar; o resumo foi movido para a barra de status.
- Controles de workspace ficam expostos em botões compactos: Book, Inspetor, Erros, Responsivo e Foco.
- Ferramentas Converter, Lang e Tema ficam expostas diretamente, sem depender do menu/overflow.
- A barra de Layout continua contextual e aparece somente quando há múltiplas quests selecionadas.

### Ferramentas de edição de quest
- A navbar agora expõe diretamente: Nova Quest, Propriedades, Título, Descrição, Dependências, Tasks, Rewards, Copiar ID, Duplicar, Excluir e Salvar.
- `Ctrl+E` abre propriedades, `F2` edita o título e `Ctrl+S` salva a quest atual.
- Dependências muda automaticamente para edição em lote quando há múltiplas quests selecionadas.
- As ações individuais ficam desabilitadas quando não há exatamente uma quest selecionada, evitando alterações acidentais.
- O menu de contexto da quest recebeu Propriedades, Título, Descrição, Dependências, Tasks, Rewards e Copiar ID.

## 0.9.0-alpha — Porting & Translation Update

### SNBT + JSON5
- Adicionado suporte de leitura/edição para Quest Books **SNBT** e **JSON5**.
- Detecção automática do formato do projeto.
- O status do projeto indica `SNBT / 1.21.1` ou `JSON5 / 26.1.2+`.
- File watcher e histórico agora acompanham arquivos `.snbt` e `.json5`.
- CRUD de quests, grupos, capítulos, dependências, tasks, rewards e posições ganhou caminhos nativos para JSON5.

### Conversor de versões
- Nova ferramenta **SNBT ↔ JSON5**.
- Conversão SNBT 1.21.1/2101.x → JSON5 26.1.2.x.
- Conversão JSON5 26.1.2.x → SNBT 1.21.1/2101.x.
- Conversão de `data`, chapter groups, chapters, reward tables e idiomas.
- Migrações conservadoras para campos conhecidos entre as versões.
- Campos desconhecidos são preservados quando podem ser representados com segurança.
- Relatório de arquivos gerados, estatísticas e avisos.
- Origem nunca é sobrescrita pelo conversor: a saída deve ser outra pasta.

### Lang Splitter integrado
- Split de idiomas SNBT por locale/tipo/capítulo.
- Merge de idiomas divididos para arquivo flat.
- Compatibilidade com o layout usado pelo Quests Lang Splitter no 1.21.1.
- Suporte de associação de `quest`, `task`, `reward`, `quest_link` e `image` ao capítulo dono.
- Backup automático antes de split/merge in-place.

### Tradução
- Loader de idiomas unificado para SNBT flat, SNBT split e JSON5 split.
- Escrita de traduções no arquivo correto conforme o formato do projeto.
- Relatórios passam a reconhecer também `task`, `reward`, `quest_link`, `image`, `chapter`, `chapter_group`, `file` e `reward_table`.
- Correção das chaves de título de tasks/rewards para o formato por ID do objeto.

### Temas e cores
- Novo menu **Ferramentas → Tema e cores**.
- Presets: Noite Teal, FTB Dark, Grafite Azul e Claro.
- Editor de cores para background, painel, inputs, accent, texto, bordas e seleção.
- Preview ao vivo e persistência por `QSettings`.

### Catálogo de itens
- Cache do catálogo atualizado para considerar a versão alvo do Minecraft.
- Projetos SNBT usam alvo 1.21.1; projetos JSON5 usam alvo 26.1.2.
- Em 26.1.2 o editor prefere o client JAR local para indexar os itens vanilla exatos, evitando usar silenciosamente uma lista remota de versão diferente.

### Compatibilidade / testes
- Novo parser/writer JSON5 sem dependência externa.
- Novo parser/writer SNBT geral com suporte ao dialeto sem vírgulas usado pelo FTB.
- Testes adicionados para JSON5, conversão nos dois sentidos, Lang Splitter, idiomas divididos e undo/redo de arquivos JSON5.
- Fluxos básicos de CRUD JSON5 validados no núcleo.

### Referência do conversor enviado pela comunidade
- O arquivo `quests.zip` enviado para comparação foi usado apenas como referência de comportamento/saída durante o desenvolvimento.
- O código dele não é incluído nem redistribuído pelo Alpha Quest Editor, pois o archive recebido não continha informação de licença.

## 0.8.0-alpha — Public Preview packaging
- Pacote preparado para GitHub e distribuição pública.
- Build Windows de um clique com `BUILD_RELEASE.bat`.
- Build Linux com `build_linux.sh`.
- PyInstaller ONEFILE para distribuição em um único executável/binário.
- GitHub Actions para testes e releases Windows/Linux por tag.
- Documentação de build, release, contribuição, segurança e terceiros.
- Checksums SHA-256 gerados pelo build local.

### Workspace responsivo
- Menu **Visualizar** na barra superior.
- Mostrar/ocultar Quest Book lateral, Inspetor e painel Problemas.
- Atalhos `Ctrl+1`, `Ctrl+2`, `Ctrl+3` e `F10` para modo foco.
- Modo responsivo automático e estado do workspace persistente.
- Barra de Layout contextual para múltipla seleção.

### Editor visual
- Seleção múltipla, alinhamento, distribuição, gaps e snap.
- Dependências em lote.
- Histórico global `Ctrl+Z/Ctrl+Y`.
- Catálogo cacheado de itens.
- Tradução/importação/exportação.
- Gerenciamento de grupos e capítulos.

### Build hotfixes 0.8
- Corrigida execução dos testes quando o projeto não está instalado como pacote.
- Workflow de GitHub Release passa o repositório explicitamente ao `gh` e suporta reexecução com `--clobber`.
- Windows/Linux passaram a gerar artefato ONEFILE.
