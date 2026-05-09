# CIOS — Branching & Release Policy

> Atualizado: Maio 2026

---

## Branches

| Branch | Propósito | Merge |
|--------|-----------|-------|
| `main` | Versão estável. Só recebe merges aos domingos. | Tag `vX.Y.Z` |
| `dev` | Desenvolvimento diário. RC (release candidate). | → main (domingo) |
| `feat/*` | Features isoladas (ex: `feat/wayland-compositor`). | → dev |

---

## Fluxo

```
feat/xyz → dev (diário, PR ou merge direto)
dev → main (domingo, após validação)
main → tag vX.Y.Z → .deb release
```

---

## Regras

### Desenvolvimento diário (seg-sáb)
- Todo trabalho acontece em `dev` ou em branches `feat/*`
- Commits em `dev` são RC (release candidates) — podem ter bugs
- Features grandes usam branch separada (`feat/wayland-compositor`)
- Merge de feat → dev quando a feature está funcional (não precisa estar perfeita)

### Release semanal (domingo)
- Merge `dev` → `main` somente se:
  1. Testes passam (pytest + ruff)
  2. Nenhum regression crítico
  3. Build .deb funciona
- Tag `vX.Y.Z` na main após merge
- GitHub Release automático via CI

### Versionamento

```
v1.0.0  → primeira release estável (já feita)
v1.1.0  → nova feature (ex: shell compositor)
v1.1.1  → bugfix
v1.2.0  → próxima feature
```

- MAJOR: mudança de paradigma (raro)
- MINOR: nova feature ou mudança significativa
- PATCH: bugfix ou polimento

---

## Workflow prático

```bash
# Desenvolvimento diário
git checkout dev
# ... trabalha ...
git commit -m "feat: implement ipc.c"
git push origin dev

# Gerar RC para testar
git tag v1.1.0-rc1
git push origin v1.1.0-rc1
# → CI roda, gera .deb, publica como pre-release

# Feature grande
git checkout -b feat/wayland-compositor
# ... trabalha por dias ...
git push origin feat/wayland-compositor
# Quando pronto: merge → dev, tag RC

# Domingo (release estável)
git checkout main
git merge dev
git tag v1.1.0
git push origin main --tags
# → CI roda, gera .deb, publica como release estável
```

---

## CI/CD

Mesmo pipeline para stable e RC:

| Trigger | Pipeline | Release |
|---------|----------|---------|
| Tag `v1.2.0` na `main` | lint → test → build → release | **Stable** (latest) |
| Tag `v1.2.0-rc1` na `dev` | lint → test → build → release | **Pre-release** (RC) |

- RC releases limpam apenas RCs anteriores (não tocam na stable)
- Stable releases limpam TUDO (RCs + stables anteriores)
- Ambos geram .deb e GitHub Release

---

*Política vigente a partir de Maio 2026.*
