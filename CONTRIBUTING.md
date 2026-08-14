# Contribuindo

Obrigado por testar ou contribuir com o Alpha Quest Editor.

## Antes de abrir um bug

Inclua, quando possível:
- sistema operacional;
- versão do Alpha Quest Editor;
- Minecraft / loader / FTB Quests;
- ação que causou o problema;
- mensagem de erro;
- trecho mínimo de SNBT que reproduza o problema, sem dados pessoais.

## Código

1. Faça um fork/branch.
2. Instale as dependências de `requirements.txt`.
3. Faça alterações pequenas e focadas.
4. Rode `python tests/test_core.py`.
5. Abra um Pull Request explicando o que mudou.

Evite adicionar dependências pesadas sem necessidade. O editor deve continuar conseguindo trabalhar offline depois que o ambiente Python estiver preparado.
