# Adoção por projetos consumidores

## Responsabilidades

O consumidor executa a jornada real, observa o efeito por uma fonte independente e
publica o JSON. O gate valida o contrato e vincula o documento à tentativa real do
GitHub Actions. Jornadas de negócio permanecem no consumidor.

Este guia descreve a interface reforçada por execução. O schema do JSON permanece
1.0.0, mas a chamada do workflow exige dois inputs adicionais. Uma adoção anterior
precisa atualizar tanto a chamada quanto a identidade emitida pelo produtor.

## Identidade e inputs

| Dado | Valor exigido |
| --- | --- |
| Código testado em `pull_request` | `github.event.pull_request.head.sha` |
| Código testado em `push` | `github.sha` |
| `repository` no JSON | `github.repository` |
| `environment` no JSON | O ambiente real, igual a `expected_environment` |
| `correlation_id` no JSON | `<correlation_prefix>-<github.run_id>-<github.run_attempt>` |
| `started_at` | Início real do cenário, igual ou posterior ao início da tentativa |
| `completed_at` | Fim real do cenário, posterior ou igual ao início e fora do futuro |
| `platform_ref` | SHA literal completo do `e2e-platform`, igual ao SHA em `uses` |
| `artifact_name` | Artifact produzido nesta tentativa; incluir `run_attempt` no nome |
| `evidence_file` | Caminho relativo dentro do artifact; padrão `evidence.json` |

`expected_environment` e `correlation_prefix` são obrigatórios. O prefixo aceita
1 a 80 caracteres ASCII: letra ou dígito inicial, seguido de letras, dígitos,
ponto, sublinhado ou hífen. O ambiente precisa ser explícito, não vazio e sem
espaços nas extremidades.

O produtor deve conferir o SHA do checkout efetivo antes de gravar a evidência.
Em PRs, o checkout padrão pode usar o commit de merge de teste; por isso o exemplo
abaixo seleciona o HEAD explicitamente. Alterar apenas o campo `sha` do JSON não
corrige um teste executado sobre outra versão.

Dentro do job reutilizável, `job.workflow_sha` identifica a versão real da plataforma.
Em um consumidor externo, `platform_ref` deve continuar sendo o SHA literal da
plataforma; `github.workflow_sha` do consumidor identifica outro workflow.

## Modelo de integração

O exemplo é um modelo para adaptação. `<E2E_PLATFORM_SHA>` precisa ser substituído
pelo mesmo SHA completo de 40 caracteres nos dois locais. O script de produto e
o ambiente de teste devem existir no consumidor e cumprir o contrato descrito
neste guia. As variáveis abaixo são a interface que esse produtor precisa consumir.

~~~yaml
name: Product E2E

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  actions: read

jobs:
  e2e:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
          persist-credentials: false
      - name: Executar E2E real e publicar a evidência do efeito
        env:
          E2E_REPOSITORY: ${{ github.repository }}
          E2E_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
          E2E_ENVIRONMENT: ci
          E2E_CORRELATION_ID: product-${{ github.run_id }}-${{ github.run_attempt }}
        run: ./scripts/run-product-e2e
      - uses: actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f
        with:
          name: product-e2e-${{ github.run_attempt }}
          path: artifacts/e2e/evidence.json
          if-no-files-found: error
          retention-days: 7

  evidence-gate:
    name: E2E Platform Evidence Gate
    needs: e2e
    uses: ericson-j-santos/e2e-platform/.github/workflows/e2e-evidence.yml@<E2E_PLATFORM_SHA>
    with:
      artifact_name: product-e2e-${{ github.run_attempt }}
      evidence_file: evidence.json
      platform_ref: <E2E_PLATFORM_SHA>
      expected_environment: ci
      correlation_prefix: product
~~~

As permissões `contents: read` e `actions: read` devem estar disponíveis no chamador.
O workflow reutilizável usa o token de leitura do próprio Actions para consultar a
tentativa exata. Não é necessário fornecer segredo pessoal ao gate. O produtor pode
precisar de permissões ou segredos próprios, definidos no menor escopo necessário.

A integração atual usa GitHub.com e a API `https://api.github.com`. A execução em
outros servidores é rejeitada explicitamente.

## Estrutura do documento

O schema está em [../schemas/evidence.schema.json](../schemas/evidence.schema.json).
O CLI operacional está em [../scripts/validate_evidence.py](../scripts/validate_evidence.py).

- Todos os campos do schema são explícitos; campos adicionais são rejeitados.
- `status` precisa ser `passed` para aprovação.
- Caso positivo e leitura independente são obrigatórios e precisam ter passado.
- `negative_control`, `idempotency` e `test_of_test` sempre incluem
  `applicable`, `passed` e `evidence`, mesmo quando não aplicáveis.
- Para um controle não aplicável, `passed` pode ser `null`; a justificativa deve
  explicar a decisão no registro do cenário. O validador não decide aplicabilidade.
- Datas usam RFC3339 com fuso conhecido. Datas sem fuso, offsets inválidos,
  conclusão anterior ao início ou no futuro são rejeitados.
- O arquivo tem limite de 1 MiB; chaves JSON duplicadas, UTF-8 inválido e valores
  fora dos tipos do contrato são rejeitados.

A fixture positiva do repositório serve apenas ao teste do contrato. Não deve ser
usada como evidência de um cenário de produto.

## O que é confrontado com o GitHub

O gate consulta a API da tentativa exata e compara repositório, SHA, run ID e
número da tentativa. O `run_started_at` fornecido pelo GitHub estabelece o limite
inferior de tempo da evidência. Ambiente e prefixo vêm da chamada do workflow;
não são inferidos a partir do JSON que será aprovado.

Ausência de artifact, arquivo fora de seu diretório, JSON inválido, controle falho,
identidade divergente, evidência de tentativa anterior ou indisponibilidade da API
fazem o job falhar. O gate também confere se `platform_ref` corresponde à versão
imutável do workflow que está sendo executado.

Após aprovação, publica o artifact
`e2e-gate-receipt-<artifact_name>-<run_attempt>`, contendo `receipt.json`, com
identidade, SHA da plataforma, início da tentativa e SHA-256 dos bytes aprovados.
O arquivo é relido para detectar alteração durante a validação.

O recibo comprova qual documento foi aprovado e sob qual contexto. O produtor
continua responsável por executar o cenário e conferir o efeito de negócio por
uma leitura independente.

## Repetição e recuperação

O replay na mesma tentativa deve produzir a mesma aprovação para a mesma evidência,
sem modificar o arquivo.

Uma nova tentativa usa outro `run_attempt`, outro nome de artifact e outra
correlação. A recuperação suportada deve executar novamente o produtor e seus
dependentes; use **Re-run all jobs** para repetir toda a cadeia. Reexecutar somente
um gate falho pode deixar o produtor anterior sem nova execução e deve resultar em
ausência de evidência atual ou rejeição da evidência antiga.

O rerun preserva a revisão do evento original. Antes do merge, confira que o HEAD
atual da PR continua igual ao SHA validado. Um novo commit exige novos checks e
nova evidência, e o SHA integrado precisa de validação pós-merge.

## Governança de merge

Configure a branch padrão para:

1. exigir pull request, resolução de conversas e atualização em relação à base;
2. exigir o check produtor da jornada E2E e o check de validação, usando os nomes
   realmente publicados pelo GitHub;
3. bloquear force-push e exclusão, sem bypass que contorne os controles exigidos;
4. impedir integração enquanto houver check obrigatório pendente ou falho.

No modelo acima, o nome esperado do gate é
`E2E Platform Evidence Gate / validate-evidence`; confirme o nome observado
na primeira execução antes de configurar a regra.

O verificador `scripts/verify_merge_governance.py` consulta a proteção clássica e
`GET /repos/{owner}/{repo}/rules/branches/{branch}`, que retorna regras ativas
aplicáveis à branch. Envelopes da coleção geral de rulesets são rejeitados porque
não demonstram essa aplicação. Regras em avaliação não contam como enforcement.

Seu resultado positivo cobre **configuração dos checks obrigatórios** e contém
`is_merge_authorization=false`. Ele não verifica revisões, bypass de atores,
resultados dos checks no HEAD, conflitos, atualidade da base ou autorização de merge.

A comprovação administrativa exige leitura da configuração aplicada e controle
negativo seguro: uma mudança com check obrigatório falho deve ficar bloqueada.
Siga as regras canônicas de isolamento; não use um PR deliberadamente falho contra
uma branch padrão desprotegida.

## Registros históricos de adoção

### ReqSys

Primeiro consumidor do contrato 1.0.0, rastreado em
`ericson-j-santos/reqsys-v2-enterprise-real#2012`.

### Observability Platform

Segundo consumidor do contrato 1.0.0. A jornada de logs, métricas e traces permaneceu
no repositório consumidor.

Registro pós-merge daquela versão:

- consumidor: `ericson-j-santos/observability-platform`;
- SHA: `58ea77cfc6c9847a0b7414ed0edc47fed2ff69b0`;
- run: `35897208450`;
- artifact: `observability-e2e-evidence`, ID `10767258975`;
- digest: `sha256:252462af87bc29d7509293787773916b57b29977260424b976938220b6d41dee`;
- `correlation_id`: `observability-35897208450-1`;
- resultado: `E2E_EVIDENCE_VALID`;
- rastreabilidade: `e2e-platform#2`.

Esses registros não atestam migração para a interface reforçada deste guia.
Cada consumidor precisa validar sua adoção no próprio SHA final.

## Referências oficiais

- [Contextos do GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
- [API de execuções e tentativas](https://docs.github.com/en/rest/actions/workflow-runs)
- [Regras ativas de uma branch](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch)
