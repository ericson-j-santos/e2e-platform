# Validação do TODO Global sem Notion

O teste consome, sem modificar, o gateway e o repositório PostgreSQL de
`ericson-j-santos/chatgpt-operational-rules` no SHA
`28fc1eb58b6c8163e8c4fa63a6bb0adbd1376f59`.

## Escopo e segurança

O workflow inicia PostgreSQL 16 descartável somente no runner público do GitHub.
A credencial do serviço é fictícia e exclusiva desse banco efêmero. O validador
recusa host remoto, banco/usuário diferentes, parâmetros extras na conexão e
ausência da autorização explícita de ambiente descartável. Recusa também um
banco que já tenha o schema `todo_bus`.

O processo real `services.todo_gateway.service_main` recebe somente a conexão
de teste e um token de gateway gerado em memória; variáveis `NOTION_*` são
removidas do ambiente desse processo. Não há worker Notion, segredo real,
migração do PC24x7, alteração de tarefa real nem publicação externa.

## Evidência necessária

A fase `exercise` exige HTTP real: negar leitura/gravação não autorizadas,
rejeitar conclusão sem evidência, inserir e atualizar uma tarefa, impedir
duplicidade no replay (inclusive concorrente) e listar o estado sem Notion.
Outra conexão PostgreSQL, em transação somente leitura, confere os registros.
O supervisor é reiniciado e a consulta é repetida. Essa fase ainda não é PASS.

Depois o workflow reinicia exclusivamente o contêiner PostgreSQL identificado
pelo próprio GitHub Actions. A fase `readback` confere a mudança de
`pg_postmaster_start_time()`, os mesmos registros e a consulta HTTP após novo
início do gateway. Só então a evidência recebe `status=PASS`.

O JSON inclui SHA da fonte, SHA do validador, run_id, correlation_id, casos e
registros sintéticos esperados; não inclui tokens ou conexão de banco.

## Interpretação

O teste comprova a capacidade desse código de operar sem Notion sobre um
PostgreSQL real isolado. Não comprova que o Desktop está ligado, que o gateway
canônico foi atualizado ou que o estado histórico do Notion foi migrado.
A API atual deriva a tarefa mais recente dos eventos da fila: `queue_state`
PENDING significa projeção não consumida, e não tarefa não persistida.
Não remover eventos como simples limpeza de fila antes de definir retenção
e uma projeção nativa durável. Ordenação de eventos atrasados e paginação
filtrada em grandes volumes são verificações adicionais, não cobertas aqui.
