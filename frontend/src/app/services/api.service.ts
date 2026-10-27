import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { ArticleOut, ThemeOption, TopicQueryOut } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  listThemes(): Observable<{ themes: ThemeOption[] }> {
    return this.http.get<{ themes: ThemeOption[] }>(`${this.base}/themes`);
  }

  ingestUrl(url: string, themes: string[] = []): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(`${this.base}/ingest/url`, {
      url,
      themes,
    });
  }

  ingestText(
    text: string,
    title?: string | null,
    publishedAt?: string | null,
    themes: string[] = [],
  ): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(`${this.base}/ingest/text`, {
      text,
      title: title?.trim() || null,
      published_at: publishedAt || null,
      themes,
    });
  }

  searchTopic(payload: {
    topic: string;
    date_from?: string | null;
    date_to?: string | null;
    on_date?: string | null;
    themes?: string[];
  }): Observable<TopicQueryOut> {
    return this.http.post<TopicQueryOut>(`${this.base}/search/topic`, payload);
  }
}
