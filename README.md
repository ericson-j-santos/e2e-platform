# E2E Platform

Plataforma reutilizável de validação ponta a ponta para múltiplos projetos.

## Princípios

- evidência vinculada ao SHA e ambiente corretos;
- `correlation_id` obrigatório;
- controles positivo e negativo quando aplicáveis;
- leitura independente do efeito;
- idempotência quando aplicável;
- comportamento fail-closed contra evidência ausente, ambígua ou residual;
- cenários de negócio permanecem nos repositórios consumidores.

Fonte de governança: `ericson-j-santos/chatgpt-operational-rules`.
