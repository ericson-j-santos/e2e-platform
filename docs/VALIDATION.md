# Validação, evidência e limites

## Controles permanentes

O workflow `E2E Platform CI` executa quatro jobs encadeados:

| Job | Prova produzida |
| --- | --- |
| `contract-self-test` | Testes do contrato, casos inválidos, regressões e CLI real em subprocesso isolado |
| `workflow-cli-e2e` | CLI do workflow com API real do GitHub, controles negativos, replay e leitura dos bytes |
| `reusable-gate / validate-evidence` | Download e aprovação do artifact pela versão real do workflow reutilizável |
| `gate-artifact-readback` | Download separado da evidência e do recibo; conferência de identidade e SHA-256 em um novo job |

O primeiro job também valida a fixture positiva e a sintaxe JSON do schema.
Os controles negativos exigem o erro de validação esperado. Uma exceção inesperada,
falha de importação ou crash não conta como rejeição correta.

O E2E do CLI do workflow cobre identidade divergente de repositório, SHA, ambiente
e correlação; evidência anterior à tentativa; controle declarado falho; tentativa
de sair do diretório do artifact; referência divergente da plataforma; e ausência
de credencial de leitura. O replay confere saída idêntica e ausência de alteração
dos bytes de entrada.

O job de leitura independente usa outro processo e outro diretório e não importa
o validador que produziu a aprovação. Compara repositório, SHA do consumidor,
ambiente, correlação, run, tentativa, SHA da plataforma e digest do documento.

Esse self-test usa evidência sintética identificada para validar a infraestrutura
do gate. Jornadas funcionais de consumidores precisam de seus próprios produtores
e leituras independentes.

## Governança: código e estado administrativo

As regressões do verificador de governança cobrem proteção clássica, regras ativas
aplicáveis à branch, formato inválido da API, paginação, branch com barra, identidade
divergente, lista vazia de checks e snapshots que não demonstram aplicação à branch.

O controle de API real solicita um nome de check sintético ausente e exige rejeição
pela configuração observada. Falha de rede, autorização, formato ou crash não
satisfaz esse controle. Seu resultado identifica
`GOVERNANCE_API_NEGATIVE_CONTROL_VALID` e `is_merge_authorization=false`.

Esse teste de integração somente leitura não altera a proteção e não demonstra
que a configuração administrativa esteja concluída. A issue #3 acompanha o
enforcement real. O verificador positivo também não autoriza merge.

## E2E de PostgreSQL

O workflow `TODO Native PostgreSQL Validation` exercita o gateway sobre PostgreSQL real
descartável. A evidência só recebe PASS após escrita e leitura HTTP, controles de
acesso, replay inclusive concorrente, leitura SQL por outra conexão e confirmação
dos dados após reinício do gateway e do banco.

O SHA do gateway externo é fixo e aparece separado do SHA do harness. Consulte
[todo-native-postgres.md](todo-native-postgres.md) para escopo, segurança e lacunas.

## Critério de aceite de um incremento

1. As regressões relevantes detectam o comportamento defeituoso anterior quando
   a reprodução segura está disponível.
2. Todos os jobs necessários executam de fato no HEAD final; sucesso de workflow
   com etapa necessária omitida não é comprovação.
3. Logs e artefatos são conferidos com run, tentativa e SHA explícitos.
4. O efeito tem leitura independente no mesmo ambiente e versão.
5. A política administrativa aplicada é verificada separadamente.
6. A integração passa pelas autorizações e checks exigidos; depois, o SHA
   integrado recebe nova validação.

Os workflows executam em PRs e pushes na `main`. A branch de correção usa também
o padrão `fix/e2e-gate-integrity-*` para preflight antes da abertura de PR.
Repetição da cadeia exige produzir evidência na tentativa nova, conforme
[ADOPTION.md](ADOPTION.md#repetição-e-recuperação).

## Rastreabilidade e retenção

O registro durável da issue/PR deve conter:

- objetivo e causa corrigida;
- prevenção acrescentada e controle negativo;
- HEAD final, SHA da plataforma e fontes externas fixadas;
- links observados dos runs, tentativa e conclusão de cada job necessário;
- nome, ID e digest dos artifacts, quando disponíveis;
- leitura independente e limites da prova;
- proteção aplicada ou bloqueio administrativo;
- próximo passo para integração e validação pós-merge.

Os artifacts do gate têm retenção de sete dias. Um registro de run antigo com
artifact expirado é evidência histórica; não substitui execução atual. Evidência
de branch candidata não deve ser apresentada como validação da `main` integrada.
