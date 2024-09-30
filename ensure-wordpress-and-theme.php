<?php

define( 'WP_CONTENT_DIR', dirname(__FILE__));
define( 'ABSPATH', dirname(__FILE__) . '/volumes/wp/6/' );
define( 'WP_DEBUG', 1);
define( 'WP_DEBUG_DISPLAY', 1);

define("WP_SITEURL", "https://wpn.fsd.team/{$argv[1]}/");
$_SERVER['HTTP_HOST'] = 'wpn.fsd.team';

define("DB_USER", "wp-db-user-{$argv[2]}");
define("DB_PASSWORD", "secret");
define("DB_NAME", "wp-db-{$argv[2]}");
define("DB_HOST", "mariadb-min.wordpress-test.svc");

global $table_prefix; $table_prefix = "wp_";

define("WP_ADMIN", true);
define("WP_INSTALLING", true);
require_once( ABSPATH . 'wp-settings.php' );

function ensure_db_schema () {
  require_once( ABSPATH . 'wp-admin/includes/upgrade.php' );
  if (! is_blog_installed()) {
    make_db_current_silent();
  }
  populate_options();
  populate_roles();
  wp_upgrade();
}

function ensure_admin_user ($user_name, $user_email, $user_password) {
  if (! username_exists($user_name)) {
    wp_create_user( $user_name, $user_password, $user_email );
  }
  $user = new WP_User( username_exists($user_name) );
  $user->set_role( 'administrator' );
  update_option( 'admin_email', $user_email );
}

function get_admin_user_id () {
  return 1;  // wp-cli does same
}

function ensure_blog_title ($blog_title) {
  update_option( 'blogname', $blog_title );
}

/**
 * Whatever wp_install does, that was not already done above.
 */
function ensure_other_basic_wordpress_things () {
  update_option( 'blog_public', 1 );
  update_option( 'fresh_site', 1 );
  update_option( 'siteurl', wp_guess_url() );

  wp_install_defaults( get_admin_user_id() );
  wp_install_maybe_enable_pretty_permalinks();

  flush_rewrite_rules();

  wp_cache_flush();
}

function ensure_theme ($theme_name) {
  global $wp_theme_directories; $wp_theme_directories = [];
  require_once(ABSPATH . 'wp-includes/theme.php');

  $theme = wp_get_theme($theme_name);
  print(switch_theme( $theme->get_stylesheet() ));
}

ensure_db_schema();
ensure_other_basic_wordpress_things();
ensure_admin_user("admin", "admin@exemple.com", "secret");
ensure_theme('wp-theme-2018');
