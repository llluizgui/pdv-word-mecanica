# PDV Word Mecânica 1.8.1 — instalador Windows com assinatura digital

## Situação

- O código e as funcionalidades continuam na versão **1.8.1**.
- A versão `v1.8.1-avaliacao` disponível atualmente no GitHub é **NÃO ASSINADA** e pode ser bloqueada pelo Smart App Control do Windows 11.
- Foi criado o workflow manual `.github/workflows/instalador-windows-assinado.yml`.
- **NENHUM EXE assinado está disponível apenas por ter criado o workflow.** A assinatura depende de uma identidade validada de editor e de uma assinatura pública confiável.

## Por que o instalador era bloqueado?

O diagnóstico no Windows do cliente mostrou evento Code Integrity 3077 relacionado à política `VerifiedAndReputableDesktop`. O arquivo do Inno Setup e a cópia temporária `.tmp` não tinham assinatura Authenticode.

Assinar apenas o EXE final **não basta** para este problema. O workflow novo usa `SignTool=pdvsign` e `SignedUninstaller=yes` na etapa Inno, para que o setup, as cópias temporárias e o desinstalador recebam assinatura válida.

Referências oficiais:
- https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm
- https://jrsoftware.org/ishelp/topic_setup_signtool.htm
- https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control
- https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-signing-integrations

## Pré-requisitos obrigatórios para gerar um EXE assinado

1. Obter um serviço/certificado de **assinatura de código com confiança pública** no nome do editor legalmente habilitado.
2. Para o workflow fornecido, ter uma conta **Microsoft Artifact Signing** aprovada, com identidade validada, perfil de certificado público e atribuição da função *Artifact Signing Certificate Profile Signer*. Verificar a elegibilidade regional e documental com a Microsoft: a existência de um endpoint no Brasil não garante elegibilidade para certificados de confiança pública.
3. Criar uma identidade de aplicativo Microsoft Entra com acesso à assinatura e autorização **OIDC do GitHub** para este repositório (sem guardar senha no projeto).
4. Configurar os seguintes **GitHub Actions Secrets**:
   - `AZURE_TENANT_ID`
   - `AZURE_CLIENT_ID`
   - `AZURE_SUBSCRIPTION_ID`
5. Configurar os seguintes **GitHub Actions Variables**:
   - `PDV_AS_ENDPOINT` (endpoint regional da conta)
   - `PDV_AS_ACCOUNT` (nome da conta)
   - `PDV_AS_PROFILE` (nome do perfil de certificado)
6. No GitHub: **Actions -> PDV Mecanica 1.8.1 - Windows assinado (manual) -> Run workflow**. A compilação falhará deliberadamente se qualquer credencial/assinatura/varredura necessária falhar.

## Resultado esperado após configurar o serviço

O workflow compila a versão 1.8.1 sem alterar as funcionalidades, testa as regras da versão, assina executáveis nativos, utiliza a assinatura integrada do Inno Setup, valida o Authenticode e executa uma varredura pontual do Microsoft Defender no runner.

**Somente depois de tudo passar** publica a release separada `v1.8.1-assinada`, com `PDVWord_Mecanica_Setup_1.8.1_ASSINADO.exe` e seu SHA-256.

A versão anterior não é sobrescrita. Os dados da oficina permanecem no armazenamento local, mas faça backup antes de qualquer reinstalação/atualização.

## Importante

- É proibido colocar senhas, chaves privadas ou certificados com chave privada em arquivos do repositório.
- Um certificado autoassinado de testes não resolve a confiança do Smart App Control.
- O trabalho de configuração não garante que o instalador passe em todas as políticas corporativas; validar num PC Windows 11 de teste com proteções normais.
- Não desligar Defender, UAC ou políticas de integridade de código para forçar a instalação.
- Sem autorização para Artifact Signing, é necessário buscar outro provedor de assinatura de código publicamente confiável e adaptar o assinador ao certificado/serviço contratado.
- Enquanto não houver assinatura confiável, para **testes** há o arquivo `ABRIR_PDV_1_8_1_PELO_CODIGO.bat`, que requer Python instalado e não garante execução sob políticas corporativas.
