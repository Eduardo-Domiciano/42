import { CommonModule } from '@angular/common';
import { Component, HostListener, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ArticleOut, TopicQueryOut } from '../../models/api.models';
import { ApiService } from '../../services/api.service';

type SearchMode = 'url' | 'topic';

export interface GlossaryEntry {
  term: string;
  meaning: string;
}

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './search.component.html',
  styleUrl: './search.component.css',
})
export class SearchComponent {
  private readonly api = inject(ApiService);

  mode: SearchMode = 'topic';
  url = '';
  topic = '';
  dateFrom = '';
  dateTo = '';
  onDate = '';

  loading = false;
  error: string | null = null;
  articleResult: ArticleOut | null = null;
  topicResult: TopicQueryOut | null = null;
  /** IDs de publicações abertas na lista do tema */
  expandedArticleIds = new Set<number>();

  glossaryOpen = false;
  paramsOpen = false;

  /** Critérios de aceite na busca por tema (espelha o backend). */
  readonly paramsRelevant: string[] = [
    'Camada 1 (claro sim): tokens do tema no texto + score lexical ≥ 0,30 (título vale mais que corpo).',
    'Também aceita: frase do tema no texto; muitos tokens no título; ou embeddings (semântico ≥ 0,48) com algum overlap.',
    'Camada 2 (zona cinza): soft lexical — algum overlap real e score ≥ 0,20.',
    'Período De/Até/uma data: publicação do artigo dentro do intervalo (máx. 1 mês entre De e Até).',
  ];

  /** Critérios de descarte na busca por tema. */
  readonly paramsDiscarded: string[] = [
    'Zero tokens do tema e score muito baixo → lixo óbvio, descartado sem LLM.',
    'Soft lexical não alcançado (poucos tokens / score baixo).',
    'Com período: sem data de publicação ou data fora do intervalo.',
    'Busca web bloqueada (DuckDuckGo rate-limit) → sem URLs novas; só acervo local entra no filtro.',
    'Falha ao baixar a página (fetch) → URL não vira artigo.',
  ];

  /** Termos da UI com significado curto (EN + PT). */
  readonly glossaryEntries: GlossaryEntry[] = [
    {
      term: 'Bias (viés / parcialidade)',
      meaning:
        'Tendência editorial da fonte (esquerda, centro, direita, institucional). Não julga se a matéria é falsa; só indica orientação habitual.',
    },
    {
      term: 'Ownership (grupo dono)',
      meaning:
        'Quem controla o veículo (grupo de mídia, governo, partido). Ajuda a ver se várias “fontes” na verdade são o mesmo dono.',
    },
    {
      term: 'Claims / F3 (afirmativas)',
      meaning:
        'Frases checáveis tiradas do texto (“X fez Y”). O F3 avalia cada afirmativa só com o que está na própria matéria.',
    },
    {
      term: 'Tabela Claims (colunas)',
      meaning:
        'Cada linha é uma afirmativa. Claim = texto canônico. Veredito = conclusão isolada. Confiança = certeza do veredito (0%–100%). Temporal / Geográfico / Partidário / Distorção / Suporte = notas 0,00–1,00. Método = como foi calculado (heurística, LLM, NLI…).',
    },
    {
      term: 'Escala das notas (mín. e máx.)',
      meaning:
        'Notas numéricas vão de 0,00 (mínimo) a 1,00 (máximo). Confiança aparece em porcentagem: 0% a 100% (equivale a 0,00–1,00). Valores no meio são parciais — não são “nota escolar”, e sim intensidade do sinal.',
    },
    {
      term: 'Temporal (âncora de tempo)',
      meaning:
        '0,00 = sem data/período útil. 1,00 = afirmativa bem ancorada no tempo (data no texto e/ou data de publicação do artigo). Quanto maior, mais clara a “quando”.',
    },
    {
      term: 'Geográfico (âncora de lugar)',
      meaning:
        '0,00 = quase sem lugar/instituição. 1,00 = forte âncora de local ou entidade (ex.: Brasil, STF, Brasília). Ajuda a situar o “onde / quem institucional”.',
    },
    {
      term: 'Partidário (sinal político)',
      meaning:
        '0,00 = pouco framing político explícito. 1,00 = muitos marcadores partidários/polêmica. Aqui, alto = mais risco de enquadramento político — não é “nota boa”.',
    },
    {
      term: 'Distorção (clickbait / sensacionalismo)',
      meaning:
        '0,00 = título e corpo alinhados, tom sóbrio. 1,00 = sensacionalismo ou título pouco coerente com o corpo. Alto = alerta de distorção.',
    },
    {
      term: 'Suporte (evidência interna)',
      meaning:
        '0,00 = quase sem evidência dentro do próprio artigo. 1,00 = números, citações, links ou trechos que sustentam a afirmativa no texto. Alto = mais lastro interno (ainda sem cruzar fontes externas).',
    },
    {
      term: 'Confiança (do veredito)',
      meaning:
        '0% = veredito muito incerto. 100% = método está bem seguro daquele veredito isolado. Não prova verdade absoluta; só mede certeza da avaliação das afirmativas.',
    },
    {
      term: 'Cross-reference / F4 (cruzamento)',
      meaning:
        'Compara as afirmativas com outras matérias e fontes. O F4 monta o panorama: quem apoia, quem refuta e o nível de consenso.',
    },
    {
      term: 'Consensus (consenso entre fontes)',
      meaning:
        'Quanto as fontes independentes convergem sobre a mesma afirmativa. Poucas fontes ou o mesmo dono = consenso frágil.',
    },
    {
      term: 'Calibration (calibração F3 vs F4)',
      meaning:
        'Diferença entre o veredito isolado (só o artigo) e o consenso externo. Se divergem, a análise destaca o alerta.',
    },
    {
      term: 'Stance (posição da evidência)',
      meaning:
        'Se outra matéria apoia (supports), refuta (refutes), só se relaciona (related) ou não fala do mesmo ponto (unrelated).',
    },
    {
      term: 'Primary veto (veto de fonte oficial)',
      meaning:
        'Quando existe documento ou fonte primária/oficial no conjunto, o veredito fica mais cauteloso se ela contradisser o resto.',
    },
    {
      term: 'Score (pontuação) e Tier (nível)',
      meaning:
        'Score resume confiança/qualidade heurística. Tier classifica a autoridade da fonte (primária, secundária, baixa…).',
    },
    {
      term: 'Framing (enquadramento)',
      meaning:
        'Como a história é contada: o que é enfatizado, omitido ou dramatizado, independentemente dos fatos citados.',
    },
    {
      term: 'Acervo (cache)',
      meaning:
        'Análise já gravada no banco e reutilizada. Evita baixar e recalcular o mesmo artigo se o conteúdo não mudou.',
    },
    {
      term: 'Vereditos (Supported / Disputed / Insufficient)',
      meaning:
        'Supported: há suporte interno. Disputed: há tensão ou contestação. Insufficient: falta evidência checável no texto.',
    },
  ];

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.glossaryOpen) {
      this.closeGlossary();
    } else if (this.paramsOpen) {
      this.closeParams();
    }
  }

  private lockBodyScroll(): void {
    document.body.style.overflow = 'hidden';
  }

  private unlockBodyScroll(): void {
    document.body.style.overflow = '';
  }

  openGlossary(): void {
    this.paramsOpen = false;
    this.glossaryOpen = true;
    this.lockBodyScroll();
  }

  closeGlossary(): void {
    this.glossaryOpen = false;
    if (!this.paramsOpen) {
      this.unlockBodyScroll();
    }
  }

  openParams(): void {
    this.glossaryOpen = false;
    this.paramsOpen = true;
    this.lockBodyScroll();
  }

  closeParams(): void {
    this.paramsOpen = false;
    if (!this.glossaryOpen) {
      this.unlockBodyScroll();
    }
  }

  setMode(mode: SearchMode): void {
    this.mode = mode;
    this.error = null;
  }
  isArticleExpanded(id: number): boolean {
    return this.expandedArticleIds.has(id);
  }

  toggleArticle(id: number, event?: Event): void {
    event?.preventDefault();
    const next = new Set(this.expandedArticleIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this.expandedArticleIds = next;
  }

  /** Formato: TermoEN (tradução) */
  withPt(en: string, pt: string): string {
    return `${en} (${pt})`;
  }

  biasWord(): string {
    return this.withPt('Bias', 'viés / parcialidade');
  }

  claimsWord(): string {
    return this.withPt('Claims', 'afirmativas');
  }

  ownershipWord(): string {
    return this.withPt('Ownership', 'grupo dono');
  }

  scoreWord(): string {
    return this.withPt('Score', 'pontuação');
  }

  tierWord(): string {
    return this.withPt('Tier', 'nível de autoridade');
  }

  framingWord(): string {
    return this.withPt('Framing', 'enquadramento');
  }

  biasLabel(label: string | null | undefined): string {
    const map: Record<string, string> = {
      institutional: 'Institutional (institucional)',
      left: 'Left (esquerda)',
      center_left: 'Center-left (centro-esquerda)',
      center: 'Center (centro)',
      center_right: 'Center-right (centro-direita)',
      right: 'Right (direita)',
      unknown: 'Unknown (desconhecida)',
    };
    return map[label || 'unknown'] || label || 'Unknown (desconhecida)';
  }

  contentTypeLabel(type: string | null | undefined): string {
    const map: Record<string, string> = {
      official_document: 'Official document (documento oficial)',
      press_release: 'Press release (comunicado)',
      opinion: 'Opinion (opinião)',
      editorial: 'Editorial (editorial)',
      analysis: 'Analysis (análise)',
      post: 'Post (publicação em rede)',
      note: 'Note (nota)',
      article: 'Article (artigo)',
    };
    return map[type || 'article'] || type || 'Article (artigo)';
  }

  verdictLabel(verdict: string | null | undefined): string {
    const map: Record<string, string> = {
      supported: 'Supported (com suporte interno)',
      disputed: 'Disputed (contestável)',
      insufficient: 'Insufficient (evidência insuficiente)',
      opinion: 'Opinion (opinião)',
    };
    return map[verdict || ''] || verdict || '—';
  }

  methodLabel(method: string | null | undefined): string {
    const map: Record<string, string> = {
      heuristic: 'Heuristic (heurística / regras)',
      llm: 'LLM (modelo de IA)',
      'llm+source': 'LLM + source (IA + perfil da fonte)',
      'heuristic+claims': 'Heuristic + claims (regras + afirmativas)',
      'heuristic+nli': 'Heuristic + NLI (regras + rede neural)',
      nli: 'NLI (rede neural de entailment)',
      acervo: 'Acervo (análise reutilizada do banco)',
    };
    return map[method || ''] || method || '—';
  }

  authorityTierLabel(tier: string | null | undefined): string {
    const map: Record<string, string> = {
      primary: 'Primary (primária / oficial)',
      secondary: 'Secondary (secundária)',
      low: 'Low (baixa)',
      reputable: 'Reputable (reputável)',
    };
    if (!tier) {
      return '?';
    }
    return map[tier] || `${tier}`;
  }

  stanceLabel(stance: string | null | undefined): string {
    const map: Record<string, string> = {
      supports: 'Supports (apoia)',
      refutes: 'Refutes (refuta)',
      related: 'Related (relacionada)',
      unrelated: 'Unrelated (não relacionada)',
    };
    return map[stance || ''] || stance || '—';
  }

  crossRefWord(): string {
    return this.withPt('Cross-reference', 'cruzamento');
  }

  calibrationWord(): string {
    return this.withPt('Calibration', 'calibração F3 vs F4');
  }

  consensusWord(): string {
    return this.withPt('Consensus', 'consenso entre fontes');
  }

  vetoWord(): string {
    return this.withPt('Primary veto', 'veto de fonte oficial');
  }

  summaryParagraphs(text: string | null | undefined): string[] {
    return (text || '')
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean);
  }

  /** Blocos do resumo geral do tema (seções ## + bullets). */
  topicSummarySections(
    text: string | null | undefined,
  ): { title: string; items: { text: string; level: number }[] }[] {
    const sections: { title: string; items: { text: string; level: number }[] }[] =
      [];
    let current: { title: string; items: { text: string; level: number }[] } | null =
      null;

    for (const raw of (text || '').split('\n')) {
      const line = raw.trimEnd();
      const heading = line.match(/^##\s+(.+)$/);
      if (heading) {
        current = { title: heading[1].trim(), items: [] };
        sections.push(current);
        continue;
      }
      if (!current) {
        continue;
      }
      const nested = line.match(/^\s{2}-\s+(.+)$/);
      if (nested) {
        current.items.push({ text: nested[1].trim(), level: 2 });
        continue;
      }
      const bullet = line.match(/^-\s+(.+)$/);
      if (bullet) {
        current.items.push({ text: bullet[1].trim(), level: 1 });
      }
    }
    return sections;
  }

  /** True se Até passa de 1 mês depois de De. */
  private exceedsOneMonth(from: string, to: string): boolean {
    const start = new Date(`${from}T00:00:00`);
    const end = new Date(`${to}T00:00:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return false;
    }
    const limit = new Date(start);
    limit.setMonth(limit.getMonth() + 1);
    return end > limit;
  }

  submit(): void {
    this.error = null;
    this.articleResult = null;
    this.topicResult = null;
    this.expandedArticleIds = new Set();
    this.loading = true;

    if (this.mode === 'url') {
      if (!this.url.trim()) {
        this.loading = false;
        this.error = 'Informe uma URL de notícia.';
        return;
      }
      this.api.ingestUrl(this.url.trim()).subscribe({
        next: (result) => {
          this.articleResult = result;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail || 'Falha ao analisar a URL.';
          this.loading = false;
        },
      });
      return;
    }

    if (!this.topic.trim()) {
      this.loading = false;
      this.error = 'Informe um tema para buscar.';
      return;
    }

    if (this.dateFrom && this.dateTo) {
      if (this.dateFrom > this.dateTo) {
        this.loading = false;
        this.error = 'A data De não pode ser depois de Até.';
        return;
      }
      if (this.exceedsOneMonth(this.dateFrom, this.dateTo)) {
        this.loading = false;
        this.error = 'O intervalo entre De e Até não pode passar de 1 mês.';
        return;
      }
    }

    this.api
      .searchTopic({
        topic: this.topic.trim(),
        date_from: this.dateFrom || null,
        date_to: this.dateTo || null,
        on_date: this.onDate || null,
      })
      .subscribe({
        next: (result) => {
          this.topicResult = result;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail || 'Falha na busca por tema.';
          this.loading = false;
        },
      });
  }
}
