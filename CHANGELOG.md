# Changelog

## 0.8.0-alpha — Public Preview packaging
- Pacote preparado para GitHub e distribuição pública.
- Build Windows de um clique com `BUILD_RELEASE.bat`.
- Build Linux com `build_linux.sh`.
- PyInstaller spec versionado.
- GitHub Actions para testes e releases Windows/Linux por tag.
- Documentação de build, release, contribuição, segurança e terceiros.
- Checksums SHA-256 gerados pelo build local.

## Workspace responsivo
- Novo menu **Visualizar** na barra superior.
- Mostrar/ocultar rapidamente: Quest Book lateral, Inspetor Quest/Itens e painel Problemas.
- Atalhos: `Ctrl+1` Quest Book, `Ctrl+2` Inspetor, `Ctrl+3` Problemas, `F10` modo foco.
- Botões de recolher também ficam nos próprios painéis.
- **Modo foco** esconde os painéis e maximiza o canvas sem perder o estado anterior.
- **Modo responsivo automático** reduz painéis em janelas menores e os restaura quando há espaço novamente.
- Tamanhos dos splitters, visibilidade dos painéis, abas e preferências são lembrados entre execuções.
- As abas `Quest`, `Itens` e `Traduções` podem ser ocultadas pelo menu Visualizar sem destruir seu conteúdo.

## Barra de Layout contextual
- A barra de alinhamento/distribuição deixa de ocupar espaço o tempo todo.
- Por padrão, ela aparece somente quando existem **2 ou mais quests selecionadas**.
- Undo/Redo e a ferramenta de seleção continuam na barra principal, sempre acessíveis.
- A opção **Layout só com múltipla seleção** pode ser desligada no menu Visualizar.

## Inspetor / aba Geral
- Painel de propriedades agora aceita largura menor e usa rolagem vertical.
- Campos foram separados em seções: Informações, Aparência, Comportamento e Visibilidade/Dependências.
- Inputs ganharam altura e espaçamento maiores.
- Descrição virou área multilinha maior.
- Checkboxes ficaram explícitos e mais fáceis de ler.
- Isso corrige a sensação de campos espremidos observada na 0.7.

## Compatibilidade preservada
- Mantém seleção múltipla, alinhamento, distribuição, gaps, snap, dependências em lote, histórico global `Ctrl+Z/Ctrl+Y`, catálogo cacheado de itens, tradução/importação/exportação e gerenciamento de grupos/capítulos.

### Build hotfix
- Corrigida a execucao de `tests/test_core.py` fora de um pacote instalado.
- O teste agora adiciona a raiz do projeto ao `sys.path` antes de importar `alphaquest`.
- Windows, Linux e GitHub Actions tambem definem `PYTHONPATH` explicitamente durante os testes.

### Release workflow FIX2
- GitHub Release publish job now passes the repository explicitly to GitHub CLI.
- Release publishing no longer depends on a local `.git` checkout in the publish job.
- Re-running a tag workflow updates existing release assets with `--clobber` instead of failing.
