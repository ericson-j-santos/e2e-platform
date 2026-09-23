# Adoção por projetos consumidores

## Objetivo

O projeto consumidor executa sua jornada E2E real e publica um JSON de evidência. O `e2e-platform` valida o contrato de forma centralizada e fail-closed.

## Regras

1. O cenário de negócio permanece no repositório consumidor.
2. O consumidor publica o arquivo de evidência como artifact da mesma execução.
3. O gate reutilizável deve ser fixado por SHA completo.
4. O input `platform_ref` deve receber o mesmo SHA usado em `uses`.
5. Ausência de artifact, arquivo inválido, controle obrigatório falho ou referência mutável deve falhar o job.
6. A evidência deve pertencer ao mesmo SHA, ambiente, execução e `correlation_id` usados para declarar o E2E concluído.
7. Uma falha pós-merge invalida a conclusão até que um novo SHA integrado seja revalidado.

## Exemplo

```yaml
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Executar E2E do produto
        run: ./scripts/run-product-e2e
      - uses: actions/upload-artifact@v4
        with:
          name: e2e-evidence
          path: artifacts/e2e/evidence.json

  evidence-gate:
    needs: e2e
    uses: ericson-j-santos/e2e-platform/.github/workflows/e2e-evidence.yml@<E2E_PLATFORM_SHA>
    with:
      artifact_name: e2e-evidence
      evidence_file: evidence.json
      platform_ref: <E2E_PLATFORM_SHA>
```

Substitua `<E2E_PLATFORM_SHA>` pelo mesmo SHA completo de 40 caracteres nos dois locais.

## Campos de evidência

O contrato 1.0.0 está em `schemas/evidence.schema.json`. O validador operacional está em `scripts/validate_evidence.py`.

## Adoções comprovadas

### ReqSys

Primeiro consumidor real do contrato compartilhado. A conclusão está rastreada em `ericson-j-santos/reqsys-v2-enterprise-real#2012`.

### Observability Platform

Segundo consumidor real. A jornada existente de logs, métricas e traces permaneceu no repositório consumidor; o `e2e-platform` validou apenas o contrato de evidência.

Evidência final pós-merge:

- consumidor: `ericson-j-santos/observability-platform`;
- SHA: `58ea77cfc6c9847a0b7414ed0edc47fed2ff69b0`;
- run: `35897208450`;
- artifact: `observability-e2e-evidence`, ID `10767258975`;
- digest: `sha256:252462af87bc29d7509293787773916b57b29977260424b976938220b6d41dee`;
- `correlation_id`: `observability-35897208450-1`;
- resultado: `E2E_EVIDENCE_VALID`;
- rastreabilidade: `e2e-platform#2`.

Esse segundo consumidor comprovou que o contrato não depende de regras de negócio do ReqSys.
