# Alpha Quest Editor

**Editor desktop visual externo para FTB Quests**, feito em Python + PySide6.

> Public Preview: `v0.9.2-alpha`

O objetivo é criar, organizar, validar, traduzir e portar Quest Books sem precisar manter o Minecraft aberto. A 0.9 amplia o projeto para os dois formatos de armazenamento que estamos mirando: **SNBT (linha 1.21.1/2101.x)** e **JSON5 (linha 26.1.2.x)**.


## Mapa de Dependências

A ferramenta **Deps em lote** permite montar relações de dependência usando a seleção do canvas: capture quem é pré-requisito, capture quem recebe e aplique em lote. O modo Adicionar preserva relações existentes e toda a operação pode ser desfeita com `Ctrl+Z`.

## Principais recursos

### Editor visual
- Visualização de capítulos e quests em canvas.
- Nomes e descrições vindos dos arquivos de idioma.
- Arrastar e salvar posições `x/y`.
- Criar, duplicar e excluir quests.
- Toolbar compacta com acesso direto a Propriedades, Título, Descrição, Dependências, Tasks, Rewards, ID e Salvar.
- Gerenciar grupos e capítulos.
- Tasks, Rewards e dependências.
- Seleção múltipla e edição estrutural em lote.
- Alinhamento, distribuição, espaçamento e snap.
- Dependências em lote.
- Histórico `Ctrl+Z` / `Ctrl+Y`.

### Itens do Minecraft e mods
- Catálogo pesquisável de itens do Minecraft e mods.
- Leitura de assets/texturas dos JARs sem executar código Java.
- Cache persistente do catálogo.
- Carregamento de texturas sob demanda.
- Para 26.1.2, o editor prioriza o JAR local do cliente para obter o catálogo vanilla correto.

### Tradução
- Editor PT-BR / EN-US e suporte a outros locales presentes no projeto.
- Arquivos de idioma SNBT planos.
- Layout dividido do **Quests Lang Splitter** no 1.21.1.
- Arquivos JSON5 divididos nativamente por tipo/capítulo no 26.1.2.x.
- Exportação/importação de relatório de traduções CSV/JSON.
- Filtro de textos ausentes.

### Portabilidade SNBT ↔ JSON5
- Conversor **SNBT 1.21.1 → JSON5 26.1.2**.
- Conversor **JSON5 26.1.2 → SNBT 1.21.1**.
- Conversão de capítulos, grupos, tasks, rewards e traduções.
- Preservação conservadora de campos desconhecidos quando representáveis.
- Backup antes das operações destrutivas/in-place.
- Relatório de arquivos gerados e avisos após a conversão.

> O conversor é uma ferramenta de portabilidade em fase alpha. Sempre teste a cópia convertida no FTB Quests da versão de destino antes de substituir o projeto original.

### Lang Splitter integrado
- Dividir arquivos SNBT de idioma por locale/tipo/capítulo.
- Mesclar novamente os arquivos divididos.
- Compatibilidade de layout voltada ao fluxo do Quests Lang Splitter.
- Opção de manter o arquivo flat durante o split.

### Interface
- Workspace responsivo e painéis ocultáveis.
- Modo foco no canvas.
- Temas prontos: **Noite Teal**, **FTB Dark**, **Grafite Azul** e **Claro**.
- Editor de cores para criar um tema personalizado.
- Tema salvo entre execuções.

### Segurança e produtividade
- Validação de IDs, traduções e dependências.
- Backups automáticos.
- File watcher para alterações externas em `.snbt` e `.json5`.
- Histórico global para alterações feitas pelo editor.

## Compatibilidade alvo

| Minecraft / FTB Quests | Formato | Estado |
|---|---|---|
| Minecraft 1.21.1 + FTB Quests 2101.x | SNBT | Alvo principal / editor nativo |
| Minecraft 26.1.2 + FTB Quests 26.1.2.x | JSON5 | Alvo principal da 0.9 / editor nativo em evolução |

Outras versões podem funcionar, mas ainda não são garantia desta alpha.

## Ferramentas novas da 0.9

No menu **Ferramentas**:

```text
Ferramentas
├─ Conversor SNBT ↔ JSON5…
├─ Lang Splitter / idiomas…
└─ Tema e cores…
```

Veja [PORTING.md](PORTING.md) para o fluxo de portabilidade e tradução.

## Baixar versão pronta

Abra **Releases** no GitHub e baixe o arquivo do seu sistema:

- `AlphaQuestEditor-vX.Y.Z-Windows-x64.exe`
- `AlphaQuestEditor-vX.Y.Z-Linux-x64`

No Windows, o build oficial é **ONEFILE**: baixe um único `.exe` e execute.

## Executar pelo código-fonte

### Windows

Dê dois cliques em:

```text
run.bat
```

### Linux

```bash
chmod +x run_linux.sh
./run_linux.sh
```

## Gerar uma Release no Windows

Dê dois cliques em:

```text
BUILD_RELEASE.bat
```

O script roda os testes e cria a pasta `release/` com o executável Windows, ZIP do código-fonte e checksums.

Veja também:
- [BUILDING.md](BUILDING.md)
- [RELEASING.md](RELEASING.md)
- [PORTING.md](PORTING.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Segurança

O editor lê JARs como arquivos ZIP para descobrir assets e metadados; ele não executa o código Java dos mods durante essa indexação.

Mesmo com backups automáticos, faça uma cópia do Quest Book ao testar versões alpha, principalmente antes de conversões entre versões do FTB Quests.

## Licença

O código deste repositório está sob licença MIT. Dependências e projetos de terceiros mantêm suas próprias licenças.

## Projeto independente

Alpha Quest Editor é uma ferramenta comunitária independente. Não é um produto oficial da FTB e não possui afiliação oficial com FTB, Mojang, Microsoft ou NeoForge.
