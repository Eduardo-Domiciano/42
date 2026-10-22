import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { ArticleOut, TopicQueryOut } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  ingestUrl(url: string): Observable<ArticleOut> {
    return this.http.post<ArticleOut>(`${this.base}/ingest/url`, { url });
  }

  searchTopic(payload: {
    topic: string;
    date_from?: string | null;
    date_to?: string | null;
    on_date?: string | null;
  }): Observable<TopicQueryOut> {
    return this.http.post<TopicQueryOut>(`${this.base}/search/topic`, payload);
  }
}
