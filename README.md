# E2E Platform

Plataforma reutilizável de validação ponta a ponta para múltiplos projetos.

## Escopo

Este repositório contém apenas infraestrutura E2E transversal: contrato de evidência, validação fail-closed, workflows reutilizáveis e componentes genéricos. Jornadas, fixtures, seletores e regras de negócio permanecem nos repositórios consumidores.

## Contrato mínimo

Uma evidência aprovada deve estar vinculada a projeto, repositório, SHA, ambiente e `correlation_id`, além de comprovar:

- caso positivo;
- controle negativo quando aplicável;
- leitura independente do efeito;
- idempotência quando aplicável;
- teste do próprio teste quando declarado aplicável.

`exit code 0`, HTTP 2xx, log de sucesso ou evidência residual não substituem o efeito observado.

O gate de evidência também não substitui a governança de merge: consumidores devem proteger a branch padrão e exigir os checks E2E antes de integrar mudanças.

## Uso

Consulte `docs/ADOPTION.md`. Consumidores devem fixar o workflow por SHA completo e fornecer o mesmo SHA no input `platform_ref`.

## Governança

Fonte canônica: `ericson-j-santos/chatgpt-operational-rules`, especialmente `rules/e2e-validation.md`.

Status: contrato v1 validado em dois consumidores reais (ReqSys e Observability Platform); enforcement administrativo de merge/rulesets permanece acompanhado na issue #3.
