# Adoção por projetos consumidores

## Objetivo

O projeto consumidor executa sua jornada E2E real e publica um JSON de evidência. O `e2e-platform` valida o contrato de forma centralizada e fail-closed.

## Regras

1. O cenário de negócio permanece no repositório consumidor.
2. O consumidor publica o arquivo de evidência como artifact da mesma execução.
3. O gate reutilizável deve ser fixado por SHA completo.
4. O input `platform_ref` deve receber o mesmo SHA usado em `uses`.
5. Ausência de artifact, arquivo inválido, controle obrigatório falho ou referência mutável deve falhar o job.
6. A branch padrão do consumidor deve exigir merge via PR e tornar obrigatórios o job que produz a evidência E2E e o `E2E Platform Evidence Gate`.
7. O Evidence Gate não substitui ruleset/branch protection: sem enforcement no repositório, um check verde/vermelho pode não impedir o merge.
8. O merge só pode usar o HEAD que foi validado; se o SHA mudar, os checks e a evidência devem ser refeitos.
9. Após o merge, o SHA integrado deve ser revalidado antes de declarar o incremento concluído.

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


## Governança de merge obrigatória

O contrato de evidência e a política de merge são complementares:

- o `e2e-platform` valida se a evidência é íntegra e fail-closed;
- o repositório consumidor deve configurar a branch padrão para impedir merge enquanto os checks obrigatórios não estiverem verdes.

Configuração mínima esperada no consumidor:

1. exigir pull request para alteração da branch padrão;
2. exigir o check que executa o E2E real e publica o artifact;
3. exigir `E2E Platform Evidence Gate / validate-evidence`;
4. bloquear force-push e exclusão da branch padrão;
5. impedir uso de evidência produzida para SHA diferente do HEAD atual.

Se ruleset/branch protection não puder ser comprovado, o estado da adoção é **parcial**: a validação E2E pode estar correta, mas o enforcement de merge não está evidenciado.

### Validação negativa

Antes de considerar a governança concluída, um PR de teste com check obrigatório propositalmente falho deve permanecer não mergeável. Depois, com os mesmos checks verdes no HEAD esperado, um PR equivalente deve se tornar elegível a merge.
