# AGENTS.md

Este repositório pertence ao Engineering Control Plane e fornece infraestrutura E2E reutilizável.

Antes de alterar código:
1. consultar a branch main de `ericson-j-santos/chatgpt-operational-rules`;
2. aplicar `rules/e2e-validation.md`;
3. manter regras de negócio fora deste repositório;
4. manter comportamento fail-closed;
5. não registrar segredos ou dados confidenciais;
6. exigir referência imutável (SHA completo) para consumo entre repositórios;
7. validar caso positivo e ao menos um controle negativo do próprio validador.

Não declarar conclusão apenas por build, lint, HTTP 2xx, exit code 0 ou mensagem de log.
