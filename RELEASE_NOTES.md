# Alpha Quest Editor v0.9.8-alpha

Esta versão transforma o sistema de portabilidade em uma **matriz universal de rotas do FTB Quests**.

## Port Universal

Rotas disponíveis:

- **1.20 → 1.21**
- **1.20 → 26.1.2 direto**
- **1.20 → 1.21 → 26.1.2**, preservando a cópia intermediária
- **1.21 → 26.1.2**
- **26.1.2 → 1.21**
- **1.21 → 1.20** continua disponível como backport

O Alpha detecta automaticamente se a origem parece 1.20 (SNBT com textos inline), 1.21 (SNBT + lang externo) ou 26.1.2 (JSON5). A interface mostra apenas rotas coerentes com a origem detectada.

Na opção **1.20 → 26.1.2 direto**, uma árvore 1.21 temporária é usada internamente para externalizar as traduções antes da geração JSON5 e é removida ao final. Na opção em etapas, essa árvore 1.21 é preservada para revisão.

Cada port gera relatório por etapa e mantém a origem intacta. Recursos específicos de versão e ItemStacks legados continuam sendo tratados de forma conservadora e devem ser testados no FTB Quests de destino.

Todos os recursos da 0.9.7 e os hotfixes de estabilidade/ícones continuam incluídos. O build Windows segue ONEFILE.
