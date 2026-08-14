# Alpha Quest Editor

**Editor desktop visual externo para FTB Quests**, feito em Python + PySide6.

> Public Preview: `v0.8.0-alpha`

O objetivo é editar Quest Books sem precisar manter o Minecraft aberto, preservando a estrutura SNBT do FTB Quests e adicionando ferramentas de produtividade para autores e tradutores.

## Principais recursos

- Visualização de capítulos e quests em canvas.
- Nomes e descrições vindos dos arquivos de idioma.
- Arrastar e salvar posições `x/y`.
- Criar, duplicar e excluir quests.
- Gerenciar grupos e capítulos.
- Tasks, Rewards e dependências.
- Seleção múltipla e edição estrutural em lote.
- Alinhamento, distribuição, espaçamento e snap.
- Dependências em lote.
- Histórico `Ctrl+Z` / `Ctrl+Y`.
- Catálogo pesquisável de itens do Minecraft e mods.
- Leitura de assets/texturas de JARs sem executar código Java.
- Cache persistente do catálogo de itens.
- Editor PT-BR / EN-US.
- Exportação/importação de relatório de traduções CSV/JSON.
- Validação de IDs, traduções e dependências.
- Backups automáticos.
- Workspace responsivo, painéis ocultáveis e modo foco.

## Compatibilidade principal

- Minecraft 1.21.1
- NeoForge
- FTB Quests 2101.x

Outras versões podem funcionar, mas ainda não são o alvo principal desta alpha.

## Baixar versão pronta

Abra **Releases** no GitHub e baixe o pacote do seu sistema:

- `AlphaQuestEditor-vX.Y.Z-Windows-x64.zip`
- `AlphaQuestEditor-vX.Y.Z-Linux-x64.tar.gz` (quando disponível)

No Windows, extraia o ZIP e execute `AlphaQuestEditor.exe`.

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

O script cria a pasta `release/` com o executável Windows empacotado, código-fonte e checksums.

Veja também:
- [BUILDING.md](BUILDING.md)
- [RELEASING.md](RELEASING.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Segurança

O editor lê JARs como arquivos ZIP para descobrir assets e metadados; ele não executa o código Java dos mods durante essa indexação.

Mesmo com backups automáticos, faça uma cópia do Quest Book ao testar versões alpha.

## Licença

O código deste repositório está sob licença MIT. Dependências e projetos de terceiros mantêm suas próprias licenças.

## Projeto independente

Alpha Quest Editor é uma ferramenta comunitária independente. Não é um produto oficial da FTB e não possui afiliação oficial com FTB, Mojang, Microsoft ou NeoForge.


## Single-file builds (FIX3)
Windows releases are built with PyInstaller ONEFILE. The distributable artifact is `release/AlphaQuestEditor-v0.8.0-alpha-Windows-x64.exe`; do not distribute the temporary `build/` directory. A one-file build may start slightly slower because bundled libraries are unpacked to a temporary runtime directory.
