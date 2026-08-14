# Changelog

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
