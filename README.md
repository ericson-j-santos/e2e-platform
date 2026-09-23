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

## Consumidores validados

O contrato 1.0.0 já foi comprovado em dois consumidores independentes:

- `ericson-j-santos/reqsys-v2-enterprise-real`: primeiro piloto, rastreado em `#2012`;
- `ericson-j-santos/observability-platform`: segundo consumidor real, rastreado em `e2e-platform#2`.

A segunda adoção foi revalidada pós-merge no SHA `58ea77cfc6c9847a0b7414ed0edc47fed2ff69b0`, com `E2E_EVIDENCE_VALID` no run `35897208450`.

## Governança

Fonte canônica: `ericson-j-santos/chatgpt-operational-rules`, especialmente `rules/e2e-validation.md`.

Status: contrato 1.0.0 validado em múltiplos projetos; enforcement administrativo de merge/rulesets permanece acompanhado na issue #3.
