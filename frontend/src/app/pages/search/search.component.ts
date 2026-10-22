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
        'Cada linha é uma afirmativa. Claim = texto canônico. Veredito = conclusão F3 isolada. Conf. = confiança no veredito (0%–100%). Temporal / Geo / Partisan / Distortion / Support = notas 0,00–1,00. Método = como foi calculado (heurística, LLM, NLI…).',
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
      term: 'Geo (âncora geográfica)',
      meaning:
        '0,00 = quase sem lugar/instituição. 1,00 = forte âncora de local ou entidade (ex.: Brasil, STF, Brasília). Ajuda a situar o “onde / quem institucional”.',
    },
    {
      term: 'Partisan (sinal partidário)',
      meaning:
        '0,00 = pouco framing político explícito. 1,00 = muitos marcadores partidários/polêmica. Aqui, alto = mais risco de enquadramento político — não é “nota boa”.',
    },
    {
      term: 'Distortion (distorção / clickbait)',
      meaning:
        '0,00 = título e corpo alinhados, tom sóbrio. 1,00 = sensacionalismo ou título pouco coerente com o corpo. Alto = alerta de distorção.',
    },
    {
      term: 'Support (suporte interno)',
      meaning:
        '0,00 = quase sem evidência dentro do próprio artigo. 1,00 = números, citações, links ou trechos que sustentam a afirmativa no texto. Alto = mais lastro interno (ainda sem cruzar fontes externas).',
    },
    {
      term: 'Conf. (confiança do veredito F3)',
      meaning:
        '0% = veredito muito incerto. 100% = método está bem seguro daquele veredito isolado. Não prova verdade absoluta; só mede certeza da avaliação F3.',
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
    }
  }

  openGlossary(): void {
    this.glossaryOpen = true;
    document.body.style.overflow = 'hidden';
  }

  closeGlossary(): void {
    this.glossaryOpen = false;
    document.body.style.overflow = '';
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
