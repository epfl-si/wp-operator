<?php

class WPMediaFolder extends Plugin
{
	protected $pluginPath = "wp-media-folder/wp-media-folder.php";
	private $wpmf_use_taxonomy ='1';
	private $wpmf_gallery_image_size_value ='["thumbnail","medium","large","full"]';
	private $wpmf_padding_masonry ='5';
	private $wpmf_padding_portfolio ='10';
	private $wpmf_usegellery ='0';
	private $wpmf_useorder ='1';
	private $wpmf_create_folder ='role';
	private $wpmf_option_override ='1';
	private $wpmf_option_duplicate ='0';
	private $wpmf_active_media ='0';
	private $wpmf_folder_option2 ='1';
	private $wpmf_option_searchall ='1';
	private $wpmf_usegellery_lightbox ='0';
	private $wpmf_media_rename ='0';
	private $wpmf_patern_rename ='{sitename} - {foldername} - #';
	private $wpmf_rename_number ='0';
	private $wpmf_option_media_remove ='0';
	private $wpmf_default_dimension ='["400x300","640x480","800x600","1024x768","1600x1200"]';
	private $wpmf_selected_dimension ='["400x300","640x480","800x600","1024x768","1600x1200"]';
	private $wpmf_weight_default ='[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]';
	private $wpmf_weight_selected ='[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]';
	private $wpmf_color_singlefile ='{"bgdownloadlink":"#444444","hvdownloadlink":"#888888","fontdownloadlink":"#ffffff","hoverfontcolor":"#ffffff"}';
	private $wpmf_option_singlefile ='0';
	private $wpmf_option_sync_media ='0';
	private $wpmf_option_sync_media_external ='0';
	private $wpmf_list_sync_media ="array ()";
	private $wpmf_time_sync ='60';
	private $wpmf_lastRun_sync ='1540467937';
	private $wpmf_slider_animation ='slide';
	private $wpmf_option_mediafolder ='0';
	private $wpmf_option_countfiles ='1';
	private $wpmf_option_lightboximage ='0';
	private $wpmf_option_hoverimg ='1';
	private $wpmf_options_format_title ='a:15:{s:6:"hyphen";s:1:"1";s:6:"period";s:1:"0";s:4:"plus";s:1:"0";s:9:"ampersand";s:1:"0";s:15:"square_brackets";s:1:"0";s:14:"curly_brackets";s:1:"0";s:10:"underscore";s:1:"1";s:5:"tilde";s:1:"0";s:4:"hash";s:1:"0";s:6:"number";s:1:"0";s:14:"round_brackets";s:1:"0";s:3:"alt";s:1:"0";s:11:"description";s:1:"0";s:7:"caption";s:1:"0";s:6:"capita";s:7:"cap_all";}';
	private $wpmf_image_watermark_apply ='a:5:{s:8:"all_size";s:1:"1";s:9:"thumbnail";s:1:"0";s:6:"medium";s:1:"0";s:5:"large";s:1:"0";s:4:"full";s:1:"0";}';
	private $wpmf_option_image_watermark ='0';
	private $wpmf_watermark_position ='top_left';
	private $wpmf_watermark_image ='';
	private $wpmf_watermark_image_id ='0';
	private $wpmf_gallery_settings ="array (
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
	private $wpmf_settings ="array (
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
	private $_wpmf_import_order_notice_flag ='yes';
	private $can_compress_scripts ='0';
}
