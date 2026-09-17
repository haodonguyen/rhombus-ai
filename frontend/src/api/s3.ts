import { apiGet, apiPost } from "./client";

export interface S3Credentials {
  access_key_id: string;
  secret_access_key: string;
  bucket: string;
  region: string;
  endpoint_url?: string;
}

/** A connected bucket. `connection_id` is opaque: the keys stay on the server. */
export interface S3Connection {
  connection_id: string;
  bucket: string;
  region: string;
  demo: boolean;
  expires_in: number;
}

export interface DemoConnection {
  available: boolean;
  connection_id?: string;
  bucket?: string;
  region?: string;
  demo?: boolean;
  expires_in?: number;
}

export function connectToS3(credentials: S3Credentials): Promise<S3Connection> {
  return apiPost("/s3/connections/", credentials);
}

export function fetchDemoConnection(): Promise<DemoConnection> {
  return apiGet("/s3/connections/demo/");
}
