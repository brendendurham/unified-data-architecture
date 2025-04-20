# Kubernetes Deployment

This directory contains the Kubernetes manifests for deploying the Unified Data Architecture to a Kubernetes cluster.

## Requirements

- Kubernetes 1.25+
- kubectl
- Helm 3.0+

## Deployment

### 1. Create the namespace

```bash
kubectl create namespace uda
```

### 2. Deploy the database

```bash
helm repo add neo4j https://neo4j-contrib.github.io/neo4j-helm
helm install kg-db neo4j/neo4j -f kubernetes/neo4j-values.yaml -n uda
```

### 3. Deploy the services

```bash
kubectl apply -f kubernetes/services/ -n uda
```

### 4. Deploy the ingress

```bash
kubectl apply -f kubernetes/ingress.yaml -n uda
```

## Architecture

The Kubernetes deployment follows cloud-native best practices:

- Services are deployed as StatefulSets for persistent storage
- Secrets are managed via Kubernetes Secrets
- Horizontal Pod Autoscaling for scaling based on CPU/memory utilization
- Ingress for routing external traffic
- Persistent Volumes for database storage

## Configuration

Edit the ConfigMap in `kubernetes/services/configmap.yaml` to update environment variables for services.

## Monitoring

The deployment includes Prometheus and Grafana for monitoring:

```bash
# Deploy monitoring stack
kubectl apply -f kubernetes/monitoring/ -n uda

# Access Grafana
kubectl port-forward svc/grafana 3000:3000 -n uda
```

## High Availability

For production environments, consider:

1. Running multiple replicas of each service
2. Setting up a Neo4j cluster with read replicas
3. Configuring pod disruption budgets
4. Using node anti-affinity rules

## Scaling

Services can be scaled horizontally:

```bash
kubectl scale deployment knowledge-graph --replicas=3 -n uda
```

## Troubleshooting

### Common Issues

1. **Database connection failures**
   
   Check if Neo4j is running:
   ```bash
   kubectl get pods -l app=neo4j -n uda
   ```

2. **Service discovery problems**
   
   Verify service endpoints:
   ```bash
   kubectl get endpoints -n uda
   ```

3. **Resource constraints**
   
   Check resource usage:
   ```bash
   kubectl top pods -n uda
   ```

### Logs

View logs for a specific service:

```bash
kubectl logs -l app=knowledge-graph -n uda
```

## Backup and Restore

### Database Backup

```bash
# Create a backup
kubectl exec kg-db-neo4j-0 -n uda -- neo4j-admin dump --database=neo4j --to=/backups/neo4j-backup.dump

# Copy backup to local machine
kubectl cp kg-db-neo4j-0:/backups/neo4j-backup.dump ./neo4j-backup.dump -n uda
```

### Database Restore

```bash
# Copy backup to pod
kubectl cp ./neo4j-backup.dump kg-db-neo4j-0:/backups/neo4j-backup.dump -n uda

# Restore from backup
kubectl exec kg-db-neo4j-0 -n uda -- neo4j-admin load --database=neo4j --from=/backups/neo4j-backup.dump
```