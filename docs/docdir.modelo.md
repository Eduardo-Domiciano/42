# Modelo de `docdir.md`

Copie este conteudo para um arquivo `docdir.md` dentro da pasta que quiser documentar.
Troque os textos entre `<...>`. Remova secoes vazias.

Modelo global do usuario: `~/.cursor/templates/docdir.modelo.md`  
Em cada projeto, preferir manter uma copia em `docs/docdir.modelo.md`.

---

# `<nome-da-pasta>`

`<Uma ou duas frases: o que esta pasta faz no projeto.>`

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `<arquivo.ext>` | `<Frase curta: responsabilidade do arquivo.>` |
| `<outro.ext>` | `<Frase curta: responsabilidade do arquivo.>` |

## Subpastas

| Pasta | O que guarda |
| --- | --- |
| `<subpasta>/` | `<Frase curta: o que vive nessa subpasta.>` |

## Observacoes

- `<Opcional. Detalhe util: dependencia, cautela, ou como a pasta se liga ao resto.>`
- `<Se nao houver observacoes, apague esta secao.>`

---

## Exemplo preenchido

```markdown
# reservation-bar

Barra fixa no rodape para escolher datas e ocupacao da reserva.

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `reservation-bar.ts` | Logica do componente: liga os campos ao servico de reserva e abre o modal. |
| `reservation-bar.html` | Layout da barra: check-in, check-out, adultos, criancas e botao Reservar. |
| `reservation-bar.css` | Estilos da barra fixa no rodape. |

## Observacoes

- Nao aparece na pagina de login.
- Depende de `ReservationService` em `core/services/`.
```
