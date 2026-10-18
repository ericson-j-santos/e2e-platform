# E2E Platform

Infraestrutura reutilizável de evidência e validação ponta a ponta para múltiplos projetos.

## O que a plataforma entrega

| Componente | Responsabilidade |
| --- | --- |
| Contrato 1.0.0 | Estrutura explícita da evidência, identidade, controles e leitura independente |
| Validador e CLI | Rejeição de evidência incompleta, inconsistente ou fora do contrato |
| Workflow reutilizável | Vínculo com repositório, SHA, ambiente, run e tentativa reais do GitHub Actions |
| Recibo de validação | Identidade da execução, SHA da plataforma e SHA-256 dos bytes aprovados |
| Verificador de governança | Leitura da configuração de checks obrigatórios aplicável à branch |
| CI e E2E | Regressões, CLI real, API real, artefatos e leitura em job independente |

Jornadas, fixtures, seletores e regras de negócio permanecem nos repositórios consumidores.

## Critério de evidência aprovada

A evidência precisa identificar projeto, repositório, SHA completo, ambiente, objetivo e
correlação; conter datas com fuso explícito, em ordem e fora do futuro; e comprovar caso
positivo e leitura independente do efeito. Controle negativo, idempotência e teste do
próprio teste têm aplicabilidade explícita. Quando aplicáveis, precisam ter passado e
conter evidência não vazia. Campos desconhecidos e JSON ambíguo são rejeitados.

O CLI distingue dois escopos:

- **contract-only:** valida estrutura e consistência do documento. É útil para fixtures
  e diagnóstico, mas não vincula a evidência a uma execução real.
- **execution-bound:** exige o contexto externo completo. No workflow reutilizável,
  esse contexto vem do GitHub Actions e da API da tentativa exata; os dados do próprio
  JSON não são usados como autoridade para aprová-lo.

O gate confere o arquivo e sua origem de execução. A comprovação do efeito de negócio
continua sob responsabilidade do produtor E2E e de sua leitura independente. Um texto
afirmando sucesso não estabelece sozinho que o efeito aconteceu. A proteção dos
workflows e da branch faz parte dessa cadeia de confiança.

## Adoção

Consulte [docs/ADOPTION.md](docs/ADOPTION.md). O consumidor precisa:

1. testar e registrar o mesmo SHA;
2. publicar o artifact na tentativa atual;
3. fixar o workflow por SHA completo e repetir esse SHA em `platform_ref`;
4. fornecer `expected_environment` e `correlation_prefix`;
5. exigir os checks de produção da evidência e de validação na política de merge.

O formato de evidência permanece em 1.0.0. A interface do workflow ganhou inputs
obrigatórios: atualizar uma integração existente exige revisar o produtor e a chamada,
além de trocar o SHA da plataforma.

## Validação e operação

[docs/VALIDATION.md](docs/VALIDATION.md) descreve os controles executados pelo CI,
a leitura independente, os limites de cada prova e a recuperação por nova tentativa.

O [E2E de PostgreSQL nativo](docs/todo-native-postgres.md) usa um banco descartável,
HTTP real, leitura SQL separada e reinício do gateway e do banco. Sua fonte externa
é fixada por SHA e identificada no artefato. O teste não atesta o estado do PC24x7.

O CI roda em pull requests e em pushes na `main`. O E2E de PostgreSQL também roda
nesses eventos, permitindo validar o SHA integrado após o merge. Artefatos do gate
têm retenção de sete dias; a rastreabilidade durável do incremento deve registrar
SHA, run, tentativa, resultado e digest na issue/PR correspondente.

## Adoções históricas

O contrato 1.0.0 já foi usado por dois consumidores independentes:

- `ericson-j-santos/reqsys-v2-enterprise-real`: primeiro piloto, rastreado em `#2012`;
- `ericson-j-santos/observability-platform`: segundo consumidor, rastreado em `e2e-platform#2`.

A segunda adoção foi revalidada pós-merge no SHA
`58ea77cfc6c9847a0b7414ed0edc47fed2ff69b0`, run `35897208450`.
Esses registros comprovam as versões adotadas naquela ocasião. A migração dos
consumidores para o vínculo reforçado por tentativa requer validação própria.

## Governança

Fonte canônica: `ericson-j-santos/chatgpt-operational-rules`, especialmente
`rules/e2e-validation.md`.

A issue #3 acompanha a aplicação e a comprovação da proteção administrativa.
O verificador consulta regras ativas aplicáveis à branch, além da proteção clássica.
Seu resultado cobre a configuração dos checks exigidos e declara
`is_merge_authorization=false`: revisões, bypass, resultados no HEAD atual,
conflitos, atualização da base e autorização de merge precisam ser conferidos
separadamente.

A conclusão de um incremento exige validação no HEAD final, enforcement comprovado,
integração autorizada e revalidação no SHA integrado.
