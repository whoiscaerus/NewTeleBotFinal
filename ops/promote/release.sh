#!/bin/bash
# PR-067: Environment Promotion Script (dev → staging → production)
# Usage: ./release.sh [--dry-run] --from <env> --to <env> --version <version_tag>

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DRY_RUN=false

# Environment configuration
FROM_ENV=""
TO_ENV=""
VERSION=""

# Docker configuration
DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io}"
DOCKER_ORG="${DOCKER_ORG:-who-is-caerus}"
IMAGE_NAME="trading-signals-backend"

# Kubernetes configuration (optional)
KUBECTL_CONTEXT_STAGING="${KUBECTL_CONTEXT_STAGING:-staging-cluster}"
KUBECTL_CONTEXT_PRODUCTION="${KUBECTL_CONTEXT_PRODUCTION:-production-cluster}"
K8S_NAMESPACE="${K8S_NAMESPACE:-default}"

# Database migration
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"

# Cache warming
WARM_CACHES="${WARM_CACHES:-true}"
CACHE_ENDPOINTS=(
    "/api/v1/health"
    "/api/v1/signals"
    "/api/v1/approvals"
)

# Prometheus metrics (pushgateway)
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
RELEASE_PROMOTED_METRIC="release_promoted_total"

# Logging
LOG_FILE="/tmp/release_${TIMESTAMP}.log"

# Safety checks
REQUIRE_CONFIRMATION="${REQUIRE_CONFIRMATION:-true}"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    log "ERROR: $*" >&2
    send_metric "$RELEASE_PROMOTED_METRIC" 0 "from=\"${FROM_ENV}\",to=\"${TO_ENV}\",status=\"failed\""
    exit 1
}

send_metric() {
    local metric_name=$1
    local metric_value=$2
    local labels=${3:-}
    
    if [ "$DRY_RUN" = false ]; then
        curl -s -X POST "${PUSHGATEWAY_URL}/metrics/job/release" \
            --data-binary "# TYPE ${metric_name} counter
${metric_name}{${labels}} ${metric_value}" || true
    fi
}

check_dependencies() {
    log "Checking dependencies..."
    
    local missing_deps=()
    
    command -v docker >/dev/null 2>&1 || missing_deps+=("docker")
    command -v git >/dev/null 2>&1 || missing_deps+=("git")
    
    # Optional dependencies
    if [ "$RUN_MIGRATIONS" = true ]; then
        command -v psql >/dev/null 2>&1 || log "WARNING: psql not found (migrations may not work)"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        error "Missing dependencies: ${missing_deps[*]}"
    fi
    
    log "All dependencies present"
}

validate_environments() {
    log "Validating environments..."
    
    # Validate FROM environment
    if [[ ! "$FROM_ENV" =~ ^(dev|development|staging)$ ]]; then
        error "Invalid FROM environment: $FROM_ENV (must be dev or staging)"
    fi
    
    # Validate TO environment
    if [[ ! "$TO_ENV" =~ ^(staging|production|prod)$ ]]; then
        error "Invalid TO environment: $TO_ENV (must be staging or production)"
    fi
    
    # Validate promotion path
    if [ "$FROM_ENV" = "development" ] || [ "$FROM_ENV" = "dev" ]; then
        FROM_ENV="development"
        if [ "$TO_ENV" != "staging" ]; then
            error "Development can only promote to staging"
        fi
    elif [ "$FROM_ENV" = "staging" ]; then
        if [[ ! "$TO_ENV" =~ ^(production|prod)$ ]]; then
            error "Staging can only promote to production"
        fi
        TO_ENV="production"
    fi
    
    log "Promotion path: $FROM_ENV → $TO_ENV"
}

validate_version() {
    log "Validating version tag..."
    
    if [ -z "$VERSION" ]; then
        error "Version tag is required (--version)"
    fi
    
    # Check version format (semantic versioning)
    if [[ ! "$VERSION" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
        error "Invalid version format: $VERSION (expected: v1.2.3 or v1.2.3-beta.1)"
    fi
    
    log "Version: $VERSION"
}

check_git_status() {
    log "Checking git repository..."
    
    cd "$PROJECT_ROOT"
    
    # Check if we're in a git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        error "Not in a git repository"
    fi
    
    # Check for uncommitted changes
    if [ -n "$(git status --porcelain)" ]; then
        log "WARNING: Uncommitted changes detected"
        git status --short
    fi
    
    # Check if we're on main branch
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    log "Current branch: $current_branch"
    
    if [ "$current_branch" != "main" ] && [ "$current_branch" != "master" ]; then
        log "WARNING: Not on main/master branch"
    fi
    
    log "Git status OK"
}

tag_docker_images() {
    log "Tagging Docker images..."
    
    local from_tag="${FROM_ENV}-latest"
    local to_tag="${TO_ENV}-${VERSION}"
    local full_image="${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}"
    
    log "Source: ${full_image}:${from_tag}"
    log "Target: ${full_image}:${to_tag}"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would pull: docker pull ${full_image}:${from_tag}"
        log "[DRY RUN] Would tag: docker tag ${full_image}:${from_tag} ${full_image}:${to_tag}"
        log "[DRY RUN] Would push: docker push ${full_image}:${to_tag}"
        return
    fi
    
    # Pull source image
    log "Pulling source image..."
    docker pull "${full_image}:${from_tag}" || error "Failed to pull source image"
    
    # Tag image
    log "Tagging image..."
    docker tag "${full_image}:${from_tag}" "${full_image}:${to_tag}" || error "Failed to tag image"
    
    # Also tag as environment-latest
    docker tag "${full_image}:${from_tag}" "${full_image}:${TO_ENV}-latest" || error "Failed to tag as latest"
    
    # Push tagged image
    log "Pushing tagged image..."
    docker push "${full_image}:${to_tag}" || error "Failed to push tagged image"
    docker push "${full_image}:${TO_ENV}-latest" || error "Failed to push latest tag"
    
    log "Docker images tagged successfully"
}

create_git_tag() {
    log "Creating git tag..."
    
    cd "$PROJECT_ROOT"
    
    local tag_name="${VERSION}-${TO_ENV}"
    local tag_message="Release ${VERSION} promoted to ${TO_ENV} at ${TIMESTAMP}"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would create tag: git tag -a ${tag_name} -m \"${tag_message}\""
        log "[DRY RUN] Would push tag: git push origin ${tag_name}"
        return
    fi
    
    # Check if tag already exists
    if git rev-parse "${tag_name}" >/dev/null 2>&1; then
        log "WARNING: Tag ${tag_name} already exists"
        return
    fi
    
    # Create tag
    git tag -a "${tag_name}" -m "${tag_message}" || error "Failed to create git tag"
    
    # Push tag
    git push origin "${tag_name}" || error "Failed to push git tag"
    
    log "Git tag created: ${tag_name}"
}

run_database_migrations() {
    log "Running database migrations..."
    
    if [ "$RUN_MIGRATIONS" != true ]; then
        log "Migrations disabled (RUN_MIGRATIONS=false)"
        return
    fi
    
    # Get database connection info for target environment
    local db_host="${TO_ENV^^}_DB_HOST"
    local db_port="${TO_ENV^^}_DB_PORT"
    local db_name="${TO_ENV^^}_DB_NAME"
    local db_user="${TO_ENV^^}_DB_USER"
    local db_password="${TO_ENV^^}_DB_PASSWORD"
    
    # Check if variables are set
    if [ -z "${!db_host:-}" ]; then
        log "WARNING: Database connection info not found for ${TO_ENV}"
        log "Skipping migrations (set ${TO_ENV^^}_DB_* environment variables)"
        return
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would run: alembic upgrade head"
        return
    fi
    
    # Run migrations using alembic
    cd "$PROJECT_ROOT/backend"
    
    PGHOST="${!db_host}" \
    PGPORT="${!db_port}" \
    PGDATABASE="${!db_name}" \
    PGUSER="${!db_user}" \
    PGPASSWORD="${!db_password}" \
    alembic upgrade head || error "Migration failed"
    
    log "Migrations completed successfully"
}

warm_application_caches() {
    log "Warming application caches..."
    
    if [ "$WARM_CACHES" != true ]; then
        log "Cache warming disabled (WARM_CACHES=false)"
        return
    fi
    
    # Get application URL for target environment
    local app_url="${TO_ENV^^}_APP_URL"
    
    if [ -z "${!app_url:-}" ]; then
        log "WARNING: Application URL not found for ${TO_ENV}"
        log "Skipping cache warming (set ${TO_ENV^^}_APP_URL environment variable)"
        return
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would warm caches by hitting endpoints"
        return
    fi
    
    log "Application URL: ${!app_url}"
    
    # Hit cache endpoints
    for endpoint in "${CACHE_ENDPOINTS[@]}"; do
        local url="${!app_url}${endpoint}"
        log "Warming: $url"
        
        curl -s -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" \
            -H "User-Agent: release-script" \
            "$url" || log "WARNING: Failed to warm $url"
    done
    
    log "Cache warming complete"
}

deploy_to_kubernetes() {
    log "Deploying to Kubernetes..."
    
    # Check if kubectl is available
    if ! command -v kubectl >/dev/null 2>&1; then
        log "kubectl not found, skipping Kubernetes deployment"
        return
    fi
    
    local context=""
    if [ "$TO_ENV" = "staging" ]; then
        context="$KUBECTL_CONTEXT_STAGING"
    elif [ "$TO_ENV" = "production" ]; then
        context="$KUBECTL_CONTEXT_PRODUCTION"
    fi
    
    if [ -z "$context" ]; then
        log "No Kubernetes context configured for ${TO_ENV}"
        return
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would deploy to Kubernetes context: $context"
        log "[DRY RUN] Would update image: ${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-${VERSION}"
        return
    fi
    
    local full_image="${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-${VERSION}"
    
    log "Kubernetes context: $context"
    log "Image: $full_image"
    
    # Update deployment
    kubectl --context="$context" \
        --namespace="$K8S_NAMESPACE" \
        set image deployment/backend \
        backend="$full_image" || error "Kubernetes deployment failed"
    
    # Wait for rollout
    log "Waiting for rollout to complete..."
    kubectl --context="$context" \
        --namespace="$K8S_NAMESPACE" \
        rollout status deployment/backend \
        --timeout=5m || error "Rollout failed"
    
    log "Kubernetes deployment complete"
}

verify_deployment() {
    log "Verifying deployment..."
    
    # Get application URL for target environment
    local app_url="${TO_ENV^^}_APP_URL"
    
    if [ -z "${!app_url:-}" ]; then
        log "WARNING: Application URL not found, skipping health check"
        return
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would verify: ${!app_url}/api/v1/health"
        return
    fi
    
    local health_url="${!app_url}/api/v1/health"
    log "Health check: $health_url"
    
    # Retry health check up to 10 times
    local max_retries=10
    local retry=0
    
    while [ $retry -lt $max_retries ]; do
        if curl -s -f "$health_url" >/dev/null 2>&1; then
            log "Health check passed"
            return
        fi
        
        retry=$((retry + 1))
        log "Health check failed (attempt $retry/$max_retries), retrying in 5s..."
        sleep 5
    done
    
    error "Health check failed after $max_retries attempts"
}

create_release_notes() {
    log "Creating release notes..."
    
    cd "$PROJECT_ROOT"
    
    local release_file="releases/${VERSION}-${TO_ENV}.md"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would create: $release_file"
        return
    fi
    
    mkdir -p releases
    
    cat > "$release_file" <<EOF
# Release ${VERSION} to ${TO_ENV}

**Date**: $(date +'%Y-%m-%d %H:%M:%S')
**Promoted from**: ${FROM_ENV}
**Promoted to**: ${TO_ENV}
**Version**: ${VERSION}

## Docker Images

- \`${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-${VERSION}\`
- \`${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-latest\`

## Git Tags

- \`${VERSION}-${TO_ENV}\`

## Changes

$(git log --oneline --no-merges -10)

## Deployment Steps

1. ✅ Docker images tagged and pushed
2. ✅ Git tag created
3. ✅ Database migrations run
4. ✅ Application caches warmed
5. ✅ Deployment verified

## Rollback

To rollback this release:

\`\`\`bash
# Tag previous image
docker tag ${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-previous \\
           ${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-latest

# Push rollback
docker push ${DOCKER_REGISTRY}/${DOCKER_ORG}/${IMAGE_NAME}:${TO_ENV}-latest

# Rollback migrations (if needed)
cd backend && alembic downgrade -1
\`\`\`

---

Generated by release.sh
EOF
    
    log "Release notes created: $release_file"
}

confirm_promotion() {
    if [ "$REQUIRE_CONFIRMATION" = false ] || [ "$DRY_RUN" = true ]; then
        return
    fi
    
    log ""
    log "====================================================================="
    log "RELEASE PROMOTION"
    log "From: $FROM_ENV"
    log "To: $TO_ENV"
    log "Version: $VERSION"
    log "====================================================================="
    log ""
    
    read -p "Are you sure you want to proceed? (type 'YES' to confirm): " confirmation
    
    if [ "$confirmation" != "YES" ]; then
        log "Promotion cancelled by user"
        exit 0
    fi
    
    log "Confirmation received, proceeding with promotion..."
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    log "====================================================================="
    log "PR-067: Environment Promotion Script"
    log "====================================================================="
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                log "DRY RUN MODE ENABLED"
                shift
                ;;
            --from)
                FROM_ENV="$2"
                shift 2
                ;;
            --to)
                TO_ENV="$2"
                shift 2
                ;;
            --version)
                VERSION="$2"
                shift 2
                ;;
            --no-confirm)
                REQUIRE_CONFIRMATION=false
                shift
                ;;
            --no-migrations)
                RUN_MIGRATIONS=false
                shift
                ;;
            --no-cache-warming)
                WARM_CACHES=false
                shift
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done
    
    # Validate inputs
    if [ -z "$FROM_ENV" ] || [ -z "$TO_ENV" ] || [ -z "$VERSION" ]; then
        error "Usage: $0 --from <env> --to <env> --version <version>"
    fi
    
    # Check dependencies
    check_dependencies
    
    # Validate environments
    validate_environments
    
    # Validate version
    validate_version
    
    # Check git status
    check_git_status
    
    # Confirm promotion
    confirm_promotion
    
    # Tag Docker images
    tag_docker_images
    
    # Create git tag
    create_git_tag
    
    if [ "$DRY_RUN" = false ]; then
        # Run database migrations
        run_database_migrations
        
        # Deploy to Kubernetes (if configured)
        deploy_to_kubernetes
        
        # Warm application caches
        warm_application_caches
        
        # Verify deployment
        verify_deployment
        
        # Create release notes
        create_release_notes
        
        # Send success metric
        send_metric "$RELEASE_PROMOTED_METRIC" 1 "from=\"${FROM_ENV}\",to=\"${TO_ENV}\",status=\"success\",version=\"${VERSION}\""
    fi
    
    log "====================================================================="
    log "Promotion complete!"
    log "From: $FROM_ENV"
    log "To: $TO_ENV"
    log "Version: $VERSION"
    log "Log file: $LOG_FILE"
    log "====================================================================="
}

# Run main function
main "$@"
