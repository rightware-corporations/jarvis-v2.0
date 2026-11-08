# Proveniência

- Origem: https://github.com/open-jarvis/OpenJarvis
- Revisão escolhida: `f21d902f4d3bd7f0f3f138f1a4613019a394b549`.
- Forma de inclusão: Git submodule `vendor/openjarvis`, sem patches upstream nesta entrega.
- Licença upstream: Apache-2.0, preservada em `vendor/openjarvis/LICENSE`.
- A revisão foi usada no ensaio real anterior de 06/11/2026, descrito no chat e no relatório RIGHTWARE_OpenJarvis_Teste_Sem_Claude_2026-11-06.md. Esse ensaio não valida automaticamente este novo wrapper.
- Os workflows upstream ficam dentro do submódulo; não são workflows activos do repositório RIGHTWARE.
- Modelos, vozes, binários e dependências têm licenças próprias. Não estão incluídos como pesos neste repositório.
- Antes de actualizar: rever diff e licenças, testar o percurso real, alterar o gitlink e PIN em rightware/runtime.py juntos, registar a evidência.
