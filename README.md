# Alpha Quest Editor

**Editor desktop visual externo para FTB Quests**, feito em Python + PySide6.

> Public Preview: `v0.9.5-alpha`

O objetivo é criar, organizar, validar, traduzir e portar Quest Books sem precisar manter o Minecraft aberto. A partir da 0.9.4 o projeto adota uma arquitetura **version-tolerant**: o scanner de JARs/KubeJS não depende de uma versão fixa do Minecraft, enquanto o editor de Quest Books detecta automaticamente SNBT ou JSON5.


## Dependências e relações

A ferramenta **Deps em lote** permite montar relações de dependência usando a seleção do canvas: capture quem é pré-requisito, capture quem recebe e aplique em lote. O modo Adicionar preserva relações existentes e toda a operação pode ser desfeita com `Ctrl+Z`.

Na aba **Dependências** de uma quest o Alpha também mostra os dois sentidos da relação: **de quem esta quest depende** e **quais quests dependem dela**. A lista de dependentes é pesquisável e um duplo clique navega diretamente até a quest relacionada.

## Principais recursos

### Editor visual
- Visualização de capítulos e quests em canvas.
- Nomes e descrições vindos dos arquivos de idioma.
- Arrastar e salvar posições `x/y`.
- Criar, duplicar e excluir quests.
- Toolbar compacta com acesso direto a Propriedades, Título, Descrição, Dependências, Tasks, Rewards, ID e Salvar.
- Gerenciar grupos e capítulos.
- Tasks, Rewards e dependências nos dois sentidos (pré-requisitos + dependentes).
- Navegação direta entre quests relacionadas pelo inspetor de dependências.
- Ícones decorativos de Tasks/Checkmarks preservados e usados no preview da quest.
- Seleção múltipla e edição estrutural em lote.
- Alinhamento, distribuição, espaçamento e snap.
- Dependências em lote.
- Histórico `Ctrl+Z` / `Ctrl+Y`.

### Biblioteca universal de JARs, itens e KubeJS
- Botão **Assets** abre uma biblioteca independente: não é necessário abrir modpack nem Quest Book.
- Adicione JARs individualmente, uma pasta inteira de mods ou uma pasta KubeJS.
- Scanner não executa Java nem KubeJS; extrai recursos/metadata de forma offline e segura.
- Catálogo visual pesquisável de itens com texturas carregadas sob demanda.
- Aba **Imagens / Quest Assets** mostra PNGs de mods, resource packs e `kubejs/assets`.
- Suporte a layouts antigos e novos de assets (`models/item`, `items/*.json`, `textures/item`, `textures/items`).
- Leitura de arquivos de idioma `.json` e `.lang` para recuperar nomes dos itens.
- KubeJS Scanner reconhece registros modernos `StartupEvents.registry('item', ...)` e sintaxe legacy `item.registry`, inclusive IDs sem namespace (`kubejs:`).
- Detecta `.displayName(...)`, `.texture(...)`, `Item.of(...)`, assets customizados e imagens usadas por quests.
- Dentro de um modpack, o mesmo índice continua cacheado e compartilhado pelos editores de Task/Reward.
- Filtro **Ícones Quest** reúne ItemStacks usados apenas para aparência em quests, capítulos, grupos e Tasks (inclusive Checkmark).
- Referências visuais que não aparecem como itens normais são mantidas como entradas sintéticas para busca/auditoria.
- Componentes/modelos customizados são detectados e preservados; previews extremamente dependentes de runtime podem usar o item-base/fallback até existir um bridge de renderização.

### Tradução
- **Central de Tradução estilo Crowdin** para importar um arquivo de lang atualizado sem copiar arquivos manualmente para dentro do modpack.
- Prévia antes da importação: alterada, nova, igual ou chave desconhecida.
- QA com linha/coluna para sintaxe quebrada, strings quebradas, chaves duplicadas, placeholders/códigos, números, tags e quebras de linha.
- Chaves suspeitas recebem sugestão de uma chave existente parecida (útil para detectar um dígito faltando no ID).
- A importação roteia cada chave automaticamente ao arquivo correto em SNBT flat, SNBT split ou JSON5 split.
- Backup + `Ctrl+Z` para desfazer uma importação inteira.
- Validação dos arquivos de idioma já existentes no projeto por locale.
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

## Compatibilidade

A 0.9.4 deixa de amarrar o scanner de itens/assets a uma versão específica. JARs e KubeJS são analisados por convenções de recursos e sintaxe, então a Biblioteca de Assets pode ser usada com packs antigos e novos.

Para Quest Books, a compatibilidade é por **adaptador de formato**:

| Formato do Quest Book | Estado |
|---|---|
| SNBT | Editor nativo / famílias FTB Quests que usam SNBT |
| JSON5 | Editor nativo em evolução / famílias novas que usam JSON5 |

O Alpha tenta detectar a versão do Minecraft por `manifest.json`, Prism/MultiMC (`mmc-pack.json`/`instance.cfg`) e usa o client JAR local quando disponível. Se a versão não puder ser detectada, o scanner continua funcionando em **modo Auto**, sem inventar um catálogo vanilla de outra versão.

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
