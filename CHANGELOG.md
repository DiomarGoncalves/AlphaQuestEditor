# Changelog

## 0.9.8-alpha — Universal FTB Port Matrix

### Port Universal
- Nova aba **Port Universal** centraliza a migração entre gerações do FTB Quests.
- Detecção automática distingue **1.20.x** (SNBT com texto inline), **1.21.x** (SNBT + lang externo) e **26.1.2+** (JSON5 + lang dividido).
- Rotas suportadas: **1.20 → 1.21**, **1.20 → 26.1.2 direto**, **1.20 → 1.21 → 26.1.2** com intermediário preservado, **1.21 → 26.1.2** e **26.1.2 → 1.21**.
- Mantido o backport **1.21 → 1.20** já existente.
- A rota direta **1.20 → 26.1.2** usa internamente uma etapa 1.21 temporária para migrar traduções antes da conversão para JSON5, removendo o intermediário no final.
- A rota em etapas preserva uma cópia 1.21 ao lado do destino 26.1.2 para revisão/teste.
- Relatório consolidado mostra cada etapa executada e seus avisos.
- O botão **Port** da navbar abre diretamente a matriz universal; os conversores antigos continuam disponíveis nas abas avançadas.
- Testes adicionados para detecção de geração e round-trip 1.20 → 1.21 → 26.1.2 → 1.21.

## 0.9.8-alpha — FTB 1.20 ↔ 1.21 Port Assistant

### Portabilidade entre gerações SNBT
- Nova ferramenta **Port** na navbar e nova aba **FTB 1.20 ↔ 1.21** no Conversor.
- Análise automática identifica texto inline (estilo 1.20), idiomas externos (estilo 1.21) e projetos parcialmente migrados.
- Port **1.20 → 1.21** externaliza títulos, subtítulos e descrições para `lang/<locale>.snbt`.
- Backport **1.21 → 1.20** injeta o locale escolhido novamente no SNBT e pode remover a pasta `lang` da cópia.
- Migração inclui file, chapter groups, reward tables, chapters, quests, tasks, rewards e quest links.
- Conflitos entre texto inline e tradução externa são detectados; o `lang` existente é preservado como fonte autoritativa.
- ItemStacks com NBT legado/customizado são detectados e preservados sem conversão destrutiva.
- A origem nunca é modificada: toda operação cria uma cópia em outro destino.
- Testes de round-trip 1.20 → 1.21 → 1.20, conflito de traduções e preservação de NBT legado.

## 0.9.6.1-alpha — Performance & Vanilla Icons Hotfix

Hotfix corretivo da 0.9.6. Mantém todas as funções anteriores e corrige os dois regressos mais visíveis encontrados em packs grandes no Windows.

### Desempenho / interface
- Corrigido o cenário em que a janela podia ficar como **"Não está respondendo"** com o progresso de cache em 100%.
- Sinais do scanner agora retornam para a GUI usando conexões Qt enfileiradas, sem lambdas manipulando widgets a partir do fluxo do worker.
- Cache rápido não força mais a abertura imediata do `QProgressDialog`; o diálogo só aparece quando a indexação realmente demora.
- Thumbnails de itens agora carregam **fora da thread da interface**. Abrir a aba Itens não abre JAR/ZIP no thread principal.
- Biblioteca de Assets usa o mesmo carregamento assíncrono para previews.
- A aba Itens não materializa mais dezenas de milhares de linhas ao abrir: mostra uma janela inicial limitada e amplia conforme a pesquisa.
- A galeria de imagens também limita a população inicial.
- Cache de bytes de texturas/assets protegido para acesso concorrente.
- Novo cache `item_index_v6.json`, forçando uma indexação limpa após o hotfix.

### Ícones vanilla / Minecraft
- Melhorada a descoberta do JAR cliente do Minecraft em layouts do Launcher oficial, Prism Launcher e MultiMC.
- Suporte a layouts compartilhados de `libraries/com/mojang/minecraft/...` além de `versions/<versão>/<versão>.jar`.
- Busca de fallback limitada em pastas `libraries`, verificando se o JAR realmente contém `assets/minecraft` e texturas de itens.
- O JAR vanilla é indexado em modo enxuto: os itens/modelos/texturas necessários são lidos sem colocar todos os assets de GUI do Minecraft no catálogo principal.
- Novo fallback manual em **Ajuda → Configurar JAR vanilla / texturas…** para launchers/customizações que não seguem os layouts conhecidos.
- O caminho manual fica salvo e pode ser usado para reindexar imediatamente.

### Segurança / compatibilidade
- Mantidas escrita atômica, logs, recuperação de arquivo inválido, QA de tradução, SNBT/JSON5, KubeJS, Dependency Mapper e todos os recursos da 0.9.6.
- Adicionado teste de regressão simulando a estrutura compartilhada de bibliotecas do Prism e validando o preview de `minecraft:apple`.
