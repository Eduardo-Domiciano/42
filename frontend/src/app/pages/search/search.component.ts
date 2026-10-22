import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ArticleOut, TopicQueryOut } from '../../models/api.models';
import { ApiService } from '../../services/api.service';

type SearchMode = 'url' | 'topic';

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
