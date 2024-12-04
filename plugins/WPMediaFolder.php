<?php

class WPMediaFolderPlugin extends Plugin
{
  protected $pluginPath = "wp-media-folder/wp-media-folder.php";
  protected $wpmf_use_taxonomy ='1';
  protected $wpmf_gallery_image_size_value ='["thumbnail","medium","large","full"]';
  protected $wpmf_padding_masonry ='5';
  protected $wpmf_padding_portfolio ='10';
  protected $wpmf_usegellery ='0';
  protected $wpmf_useorder ='1';
  protected $wpmf_create_folder ='role';
  protected $wpmf_option_override ='1';
  protected $wpmf_option_duplicate ='0';
  protected $wpmf_active_media ='0';
  protected $wpmf_folder_option2 ='1';
  protected $wpmf_option_searchall ='1';
  protected $wpmf_usegellery_lightbox ='0';
  protected $wpmf_media_rename ='0';
  protected $wpmf_patern_rename ='{sitename} - {foldername} - #';
  protected $wpmf_rename_number ='0';
  protected $wpmf_option_media_remove ='0';
  protected $wpmf_default_dimension ='["400x300","640x480","800x600","1024x768","1600x1200"]';
  protected $wpmf_selected_dimension ='["400x300","640x480","800x600","1024x768","1600x1200"]';
  protected $wpmf_weight_default ='[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]';
  protected $wpmf_weight_selected ='[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]';
  protected $wpmf_color_singlefile ='{"bgdownloadlink":"#444444","hvdownloadlink":"#888888","fontdownloadlink":"#ffffff","hoverfontcolor":"#ffffff"}';
  protected $wpmf_option_singlefile ='0';
  protected $wpmf_option_sync_media ='0';
  protected $wpmf_option_sync_media_external ='0';
  protected $wpmf_list_sync_media ="array ()";
  protected $wpmf_time_sync ='60';
  protected $wpmf_lastRun_sync ='1540467937';
  protected $wpmf_slider_animation ='slide';
  protected $wpmf_option_mediafolder ='0';
  protected $wpmf_option_countfiles ='1';
  protected $wpmf_option_lightboximage ='0';
  protected $wpmf_option_hoverimg ='1';
  protected $wpmf_options_format_title = array (
    'hyphen' => '1',
    'period' => '0',
    'plus' => '0',
    'ampersand' => '0',
    'square_brackets' => '0',
    'curly_brackets' => '0',
    'underscore' => '1',
    'tilde' => '0',
    'hash' => '0',
    'number' => '0',
    'round_brackets' => '0',
    'alt' => '0',
    'description' => '0',
    'caption' => '0',
    'capita' => 'cap_all',
  );
  protected $wpmf_image_watermark_apply = array (
    'all_size' => '1',
    'thumbnail' => '0',
    'medium' => '0',
    'large' => '0',
    'full' => '0',
  );
  protected $wpmf_option_image_watermark ='0';
  protected $wpmf_watermark_position ='top_left';
  protected $wpmf_watermark_image ='';
  protected $wpmf_watermark_image_id ='0';
  protected $wpmf_gallery_settings ="array (
        hyphen => 1,
        period => 0,
        plus => 0,
        ampersand => 0,
        square_brackets => 0,
        curly_brackets => 0,
        underscore => 1,
        tilde => 0,
        hash => 0,
        number => 0,
        round_brackets => 0,
        alt => 0,
        description => 0,
        caption => 0,
        capita => cap_all,
      )";
  protected $wpmf_settings = "array (
        hide_remote_video => 0,
        gallery_settings =>
          array (
            theme =>
              array (
                default_theme =>
                  array (
                    columns => 3,
                    size => medium,
                    targetsize => large,
                    link => file,
                    orderby => post__in,
                    order => ASC,
                  ),
                portfolio_theme =>
                  array (
                    columns => 3,
                    size => medium,
                    targetsize => large,
                    link => file,
                    orderby => post__in,
                    order => ASC,
                  ),
                masonry_theme =>
                  array (
                    columns => 3,
                    size => medium,
                    targetsize => large,
                    link => file,
                    orderby => post__in,
                    order => ASC,
                  ),
                slider_theme =>
                  array (
                    columns => 3,
                    size => medium,
                    targetsize => large,
                    link => file,
                    orderby => post__in,
                    animation => slide,
                    duration => 4000,
                    order => ASC,
                    auto_animation => 1,
                  ),
              ),
          ),
        watermark_exclude_folders =>
          array (
            0 => 0,
          ),
        folder_design => material_design,
        load_gif => 1,
        hide_tree => 1,
        watermark_margin =>
          array (
            top => 0,
            right => 0,
            bottom => 0,
            left => 0,
          ),
        watermark_image_scaling => 100,
        format_mediatitle => 1,
      )";
  protected $_wpmf_import_order_notice_flag ='yes';
  protected $can_compress_scripts ='0';
}
