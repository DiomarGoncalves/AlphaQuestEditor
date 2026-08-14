# Alpha Quest Editor v0.9.2-alpha — Dependency Mapper

## Novo na 0.9.2

- Nova ferramenta **Deps em lote** diretamente na navbar, ao lado de Tema.
- Novo **Mapa de Dependências** não modal: continue selecionando quests no canvas enquanto a ferramenta permanece aberta.
- Capture um conjunto como **Dependências (pré-requisitos)** e outro como **Quem recebe (dependentes/codependências)**.
- Suporte N→M: várias dependências podem alimentar uma ou várias quests em uma única ação.
- **Adicionar sem substituir** preserva dependências existentes; **Remover esta relação** remove apenas o vínculo selecionado.
- Prévia mostra `dependências → dependentes` e a quantidade total de relações processadas.
- `Ctrl+Z` desfaz a operação inteira de uma vez.
- Bloqueio de auto-dependência quando a mesma quest aparece nos dois lados.
- Botão **Trocar lados** para inverter rapidamente o sentido da montagem.

Também permanecem as melhorias da 0.9.1: navbar compacta e ações diretas de edição de quest.

A 0.9 amplia o Alpha Quest Editor para autores e tradutores que trabalham entre gerações do FTB Quests.

## Destaques

- Suporte a Quest Books **SNBT** e **JSON5**.
- Alvo SNBT: Minecraft 1.21.1 + FTB Quests 2101.x.
- Alvo JSON5: Minecraft 26.1.2 + FTB Quests 26.1.2.x.
- Conversor **SNBT ↔ JSON5** integrado.
- Split/merge de idiomas no estilo **Quests Lang Splitter** para 1.21.1.
- Leitura e edição de idiomas JSON5 divididos nativamente.
- Exportação/importação de tradução continua funcionando nos dois layouts.
- Temas personalizáveis e quatro presets iniciais.
- Undo/redo e file watcher agora cobrem `.json5` além de `.snbt`.
- Catálogo de itens considera a versão alvo do projeto.

## Conversão

O conversor gera uma cópia em uma pasta de destino diferente e mostra um relatório de avisos. A ferramenta é conservadora e preserva dados desconhecidos quando possível, mas esta ainda é uma alpha: **teste o Quest Book convertido no FTB Quests da versão de destino antes de substituir os arquivos originais**.

## Quests Lang Splitter

O editor pode dividir/mesclar idiomas SNBT por locale, categoria e capítulo, facilitando versionamento e trabalho de tradutores no 1.21.1.

## Temas

Abra **Ferramentas → Tema e cores** para escolher Noite Teal, FTB Dark, Grafite Azul, Claro ou montar uma paleta personalizada.

## Build

Windows e Linux continuam usando builds PyInstaller ONEFILE. O Windows é distribuído como um único `.exe`.

## Aviso

Alpha Quest Editor é uma ferramenta comunitária independente e não é um produto oficial da FTB.
